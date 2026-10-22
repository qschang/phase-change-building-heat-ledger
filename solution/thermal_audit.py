#!/usr/bin/env python3
import json, math, os, sys, tempfile
K0=273.15
def num(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x): raise ValueError('finite number required')
    return float(x)
def validate(d):
    if not isinstance(d,dict) or set(d)!={'building','heat_pump','segments'}: raise ValueError('top-level')
    b,h,segs=d['building'],d['heat_pump'],d['segments']
    if not isinstance(b,dict) or set(b)!={'nodes','links','sigma_W_per_m2_K4'}: raise ValueError('building')
    if not isinstance(segs,list) or not 1<=len(segs)<=96: raise ValueError('segments')
    sigma=num(b['sigma_W_per_m2_K4']);
    if sigma<=0: raise ValueError('sigma')
    nk={'id','C_sensible_J_per_K','latent_heat_J','transition_mid_C','transition_width_K','G_out_W_per_K','area_m2','T_initial_C','heat_fraction'}
    if not isinstance(b['nodes'],list) or not 2<=len(b['nodes'])<=8: raise ValueError('nodes')
    nodes=[]; idx={}
    for r in b['nodes']:
        if not isinstance(r,dict) or set(r)!=nk: raise ValueError('node fields')
        ident=r['id']
        if not isinstance(ident,str) or not ident or ident in idx: raise ValueError('node id')
        n={k:num(r[k]) for k in nk if k!='id'}; n['id']=ident
        if n['C_sensible_J_per_K']<=0 or n['latent_heat_J']<0 or n['transition_width_K']<=0 or n['G_out_W_per_K']<0 or n['area_m2']<0 or n['heat_fraction']<0: raise ValueError('node range')
        idx[ident]=len(nodes); nodes.append(n)
    if abs(sum(n['heat_fraction'] for n in nodes)-1)>1e-12: raise ValueError('fractions')
    seen=set()
    for r in b['links']:
        if not isinstance(r,dict) or set(r)!={'a','b','G_W_per_K'}: raise ValueError('link fields')
        if r['a'] not in idx or r['b'] not in idx or r['a']==r['b']: raise ValueError('link endpoints')
        g=num(r['G_W_per_K']); p=tuple(sorted((r['a'],r['b'])))
        if g<=0 or p in seen: raise ValueError('link range')
        seen.add(p)
    hk={'Q_nominal_W','COP_nominal','T_source_nominal_C','T_supply_nominal_C','evaporator_approach_K','condenser_approach_K','capacity_slope_per_K','capacity_reference_C','part_load_coefficients'}
    if not isinstance(h,dict) or set(h)!=hk: raise ValueError('hp fields')
    hp={k:num(h[k]) for k in hk if k!='part_load_coefficients'}; c=h['part_load_coefficients']
    if not isinstance(c,list) or len(c)!=3: raise ValueError('coefficients')
    c=[num(x) for x in c]
    if hp['Q_nominal_W']<=0 or hp['COP_nominal']<=1 or hp['evaporator_approach_K']<0 or hp['condenser_approach_K']<0: raise ValueError('hp range')
    if hp['T_source_nominal_C']+K0-hp['evaporator_approach_K']<=0 or hp['T_supply_nominal_C']+K0+hp['condenser_approach_K']<=hp['T_source_nominal_C']+K0-hp['evaporator_approach_K']: raise ValueError('nominal lift')
    total=0
    for s in segs:
        if not isinstance(s,dict) or set(s)!={'duration_s','T_outdoor_C','T_radiant_C','T_supply_C','heat_command','gains_W_by_node'}: raise ValueError('segment fields')
        dur=num(s['duration_s']); y=num(s['heat_command']); gains=s['gains_W_by_node']
        for x in [s['T_outdoor_C'],s['T_radiant_C'],s['T_supply_C']]: num(x)
        if dur<=0 or not 0<=y<=1 or not isinstance(gains,list) or len(gains)!=len(nodes): raise ValueError('segment range')
        for x in gains: num(x)
        te=num(s['T_outdoor_C'])+K0-hp['evaporator_approach_K']; tc=num(s['T_supply_C'])+K0+hp['condenser_approach_K']
        if te<=0 or tc<=te or c[0]+c[1]*y+c[2]*y*y<=0: raise ValueError('operating condition')
        total+=dur
    if total>86400+1e-9: raise ValueError('horizon')
    return nodes,b['links'],sigma,hp,c,segs,idx
def stored(n,t): return n['C_sensible_J_per_K']*t+n['latent_heat_J']*.5*(1+math.tanh((t-n['transition_mid_C'])/n['transition_width_K']))
def main(inp,out):
    with open(inp,encoding='utf-8') as f: d=json.load(f)
    nodes,links,sigma,h,c,segs,idx=validate(d); t=[n['T_initial_C'] for n in nodes]; ext={n['id']:{'min_C':t[i],'max_C':t[i]} for i,n in enumerate(nodes)}; rows=[]
    for s in segs:
        y=s['heat_command']; te0=h['T_source_nominal_C']+K0-h['evaporator_approach_K']; tc0=h['T_supply_nominal_C']+K0+h['condenser_approach_K']; eta=h['COP_nominal']/(tc0/(tc0-te0)); te=s['T_outdoor_C']+K0-h['evaporator_approach_K']; tc=s['T_supply_C']+K0+h['condenser_approach_K']; cop=None if y==0 else eta*(tc/(tc-te))*(c[0]+c[1]*y+c[2]*y*y); avail=h['Q_nominal_W']*max(0,1+h['capacity_slope_per_K']*(s['T_outdoor_C']-h['capacity_reference_C'])); q=avail*y; e=0 if cop is None else q/cop; dur=s['duration_s']; steps=max(1,math.ceil(dur/2)); dt=dur/steps; old=sum(stored(n,x) for n,x in zip(nodes,t)); outj=radj=gainj=0
        def f(x):
            rates=[0.0]*len(nodes); o=r=0.0
            for i,n in enumerate(nodes):
                co=n['G_out_W_per_K']*(s['T_outdoor_C']-x[i]); ra=n['area_m2']*sigma*((s['T_radiant_C']+K0)**4-(x[i]+K0)**4); rates[i]+=co+ra+s['gains_W_by_node'][i]+n['heat_fraction']*q; o+=co; r+=ra
            for z in links:
                a,b=idx[z['a']],idx[z['b']]; zf=z['G_W_per_K']*(x[b]-x[a]); rates[a]+=zf; rates[b]-=zf
            cap=[n['C_sensible_J_per_K']+n['latent_heat_J']*.5/n['transition_width_K']/(math.cosh((x[i]-n['transition_mid_C'])/n['transition_width_K'])**2) for i,n in enumerate(nodes)]
            return [rates[i]/cap[i] for i in range(len(nodes))],o,r
        for _ in range(steps):
            a,o1,r1=f(t); b,o2,r2=f([x+dt*y/2 for x,y in zip(t,a)]); cc,o3,r3=f([x+dt*y/2 for x,y in zip(t,b)]); d4,o4,r4=f([x+dt*y for x,y in zip(t,cc)]); t=[x+dt*(aa+2*bb+2*cc1+dd)/6 for x,aa,bb,cc1,dd in zip(t,a,b,cc,d4)]; outj+=dt*(o1+2*o2+2*o3+o4)/6; radj+=dt*(r1+2*r2+2*r3+r4)/6; gainj+=sum(s['gains_W_by_node'])*dt
        new=sum(stored(n,x) for n,x in zip(nodes,t)); res=(new-old-q*dur-gainj-outj-radj)/3.6e6
        for i,n in enumerate(nodes): ext[n['id']]['min_C']=min(ext[n['id']]['min_C'],t[i]); ext[n['id']]['max_C']=max(ext[n['id']]['max_C'],t[i])
        rows.append({'nodes':[{'id':n['id'],'end_C':t[i],'stored_energy_kWh':stored(n,t[i])/3.6e6,'phase_fraction':(0.5*(1+math.tanh((t[i]-n['transition_mid_C'])/n['transition_width_K'])) if n['latent_heat_J'] else 0.0)} for i,n in enumerate(nodes)],'heat_delivered_kWh':q*dur/3.6e6,'electricity_kWh':e*dur/3.6e6,'cop':cop,'outdoor_exchange_kWh':outj/3.6e6,'radiant_exchange_kWh':radj/3.6e6,'building_gains_kWh':gainj/3.6e6,'thermal_balance_residual_kWh':res})
    keys=['heat_delivered_kWh','electricity_kWh','outdoor_exchange_kWh','radiant_exchange_kWh','building_gains_kWh','thermal_balance_residual_kWh']; sm={k:sum(r[k] for r in rows) for k in keys}; sm['seasonal_cop']=None if sm['electricity_kWh']==0 else sm['heat_delivered_kWh']/sm['electricity_kWh']; sm['node_extrema']=ext; sm['final_stored_energy_kWh']={n['id']:stored(n,t[i])/3.6e6 for i,n in enumerate(nodes)}; sm['latent_storage_kWh']=sum(n['latent_heat_J']*0.5*(1+math.tanh((t[i]-n['transition_mid_C'])/n['transition_width_K'])) for i,n in enumerate(nodes))/3.6e6; result={'intervals':rows,'summary':sm}; folder=os.path.dirname(os.path.abspath(out)); fd,tmp=tempfile.mkstemp(prefix='.thermal-ledger-',dir=folder); os.close(fd)
    try:
        with open(tmp,'w',encoding='utf-8') as f: json.dump(result,f,separators=(',',':'),allow_nan=False)
        os.replace(tmp,out)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
if __name__=='__main__':
    try:
        if len(sys.argv)!=3: raise ValueError('usage')
        main(sys.argv[1],sys.argv[2])
    except Exception as e:
        print(str(e),file=sys.stderr); raise SystemExit(1)
