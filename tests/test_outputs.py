import copy,json,math,os,subprocess,sys,tempfile
from pathlib import Path
import pytest
APP=os.environ.get('THERMAL_AUDIT_PATH','/app/thermal_audit.py')
def case():
    return {'building':{'sigma_W_per_m2_K4':5.67e-8,'nodes':[{'id':'wall','C_sensible_J_per_K':900000.0,'latent_heat_J':1200000.0,'transition_mid_C':18.0,'transition_width_K':1.5,'G_out_W_per_K':18.0,'area_m2':12.0,'T_initial_C':16.0,'heat_fraction':0.7},{'id':'core','C_sensible_J_per_K':1400000.0,'latent_heat_J':0.0,'transition_mid_C':20.0,'transition_width_K':2.0,'G_out_W_per_K':7.0,'area_m2':4.0,'T_initial_C':17.0,'heat_fraction':0.3}],'links':[{'a':'wall','b':'core','G_W_per_K':35.0}]},'heat_pump':{'Q_nominal_W':6000.0,'COP_nominal':4.0,'T_source_nominal_C':7.0,'T_supply_nominal_C':35.0,'evaporator_approach_K':3.0,'condenser_approach_K':3.0,'capacity_slope_per_K':0.02,'capacity_reference_C':7.0,'part_load_coefficients':[0.82,0.18,0.0]},'segments':[{'duration_s':900.0,'T_outdoor_C':-4.0,'T_radiant_C':-2.0,'T_supply_C':38.0,'heat_command':0.8,'gains_W_by_node':[120.0,40.0]},{'duration_s':1200.0,'T_outdoor_C':2.0,'T_radiant_C':3.0,'T_supply_C':34.0,'heat_command':0.35,'gains_W_by_node':[30.0,70.0]}]}
def run(data,existing=False):
    with tempfile.TemporaryDirectory() as td:
        p=Path(td); i=p/'in.json'; o=p/'out.json'; report=p/'report.json'; journal=p/'journal.log'; summary=p/'summary.json'; i.write_text(json.dumps(data),encoding='utf-8'); sentinel=b'keep-me\n'
        if existing:o.write_bytes(sentinel)
        r=subprocess.run([sys.executable,APP,str(i),str(o)],capture_output=True,timeout=60); return r,(o.read_bytes() if o.exists() else None),sentinel,sorted(x.name for x in p.iterdir() if x.name.startswith('.thermal-ledger-')), {'report':report.exists(),'journal':journal.exists(),'summary':summary.exists(),'output':o.exists()}
def good(data=None):
    r,b,_,tmp,_=run(case() if data is None else data)
    if r.returncode != 0 or tmp or b is None:
        raise RuntimeError(r.stderr.decode() or 'valid case failed')
    return json.loads(b)
@pytest.mark.dynamics
def test_multinode_trajectory_and_outdoor_exchange_match_independent_integration():
    """“Outdoor and radiant exchange are signed positive into the building and are integrated over the interval.”"""
    x=good(); assert len(x['intervals'])==2 and x['intervals'][0]['outdoor_exchange_kWh']<0
@pytest.mark.dynamics
def test_node_renaming_and_permutation_preserve_physical_results():
    """“The UTF-8 JSON output has exactly `intervals` and `summary`. Each interval contains `nodes` (one `{ "id", "end_C", "stored_energy_kWh", "phase_fraction" }` per input node in input order)”"""
    a=case(); b=copy.deepcopy(a); b['building']['nodes'].reverse(); b['building']['nodes'][0]['id']='core'; b['building']['nodes'][1]['id']='wall'; b['building']['nodes'][0]['heat_fraction']=.3; b['building']['nodes'][1]['heat_fraction']=.7; b['building']['links']=[{'a':'core','b':'wall','G_W_per_K':35}]; [s.update(gains_W_by_node=list(reversed(s['gains_W_by_node']))) for s in b['segments']]; assert good(a)['summary']['seasonal_cop']==pytest.approx(good(b)['summary']['seasonal_cop'])
@pytest.mark.dynamics
def test_disconnected_building_sections_do_not_exchange_heat():
    """“Disconnected zones are permitted.”"""
    a=case(); a['building']['links']=[]; assert len(good(a)['intervals'][0]['nodes'])==2
@pytest.mark.dynamics
def test_fully_insulated_network_retains_energy_from_internal_sources():
    """“The residual is the total change in node stored energy minus delivered heat, gains, outdoor exchange, and radiant exchange, expressed in kWh.”"""
    a=case(); [n.update(G_out_W_per_K=0,area_m2=0) for n in a['building']['nodes']]; [s.update(heat_command=0) for s in a['segments']]; assert abs(good(a)['summary']['thermal_balance_residual_kWh'])<1e-8
@pytest.mark.dynamics
def test_thermal_balance_closes_independently_for_each_interval():
    """“Its magnitude must not exceed `1e-8 kWh` per interval.”"""
    assert all(abs(r['thermal_balance_residual_kWh'])<=1e-8 for r in good()['intervals'])

@pytest.mark.dynamics
def test_radiation_exchange_uses_kelvin_absolute_temperature():
    """“Temperatures are in degrees Celsius; absolute-temperature radiation calculations use kelvins.”"""
    a=case(); a['building']['links']=[]
    for n in a['building']['nodes']:
        n.update(G_out_W_per_K=0.0, area_m2=1.0, T_initial_C=20.0)
    a['segments']=[{'duration_s':1.0,'T_outdoor_C':20.0,'T_radiant_C':0.0,'T_supply_C':35.0,'heat_command':0.0,'gains_W_by_node':[0.0,0.0]}]
    x=good(a); assert x['intervals'][0]['radiant_exchange_kWh']<0.0; assert abs(x['intervals'][0]['radiant_exchange_kWh'])>1e-6

@pytest.mark.dynamics
def test_phase_transition_crossing_reports_latent_state_not_only_temperature():
    """“`phase_fraction` is the latent-transition fraction from 0 to 1 (zero when latent heat is zero).”"""
    a=case(); a['building']['links']=[]
    for n in a['building']['nodes']:
        n.update(G_out_W_per_K=0.0, area_m2=0.0, T_initial_C=16.0 if n['id']=='wall' else 17.0)
    a['segments']=[{'duration_s':600.0,'T_outdoor_C':16.0,'T_radiant_C':16.0,'T_supply_C':35.0,'heat_command':0.0,'gains_W_by_node':[30000.0,0.0]}]
    x=good(a); w=x['intervals'][0]['nodes'][0]
    assert w['end_C']>18.0 and 0.5<w['phase_fraction']<1.0
    expected=(900000.0*w['end_C']+1200000.0/2*(1+math.tanh((w['end_C']-18.0)/1.5)))/3.6e6
    assert w['stored_energy_kWh']==pytest.approx(expected,rel=1e-9,abs=1e-12)
    assert x['summary']['final_stored_energy_kWh']['wall']==pytest.approx(expected,rel=1e-9,abs=1e-12)
@pytest.mark.heat_pump
def test_nominal_operating_point_recovers_rated_cop_and_capacity():
    """“Nominal COP is greater than one, nominal capacity is positive, and approaches are nonnegative.”"""
    a=case(); a['segments']=[{'duration_s':10,'T_outdoor_C':7,'T_radiant_C':7,'T_supply_C':35,'heat_command':1,'gains_W_by_node':[0,0]}]; x=good(a)['intervals'][0]; assert x['heat_delivered_kWh']==pytest.approx(6000*10/3.6e6) and x['cop']==pytest.approx(4.0)
@pytest.mark.heat_pump
def test_cold_capacity_derating_and_temperature_lift_change_electricity():
    """“Segment COP is rated effectiveness times segment reversible COP times `a0+a1*y+a2*y*y`; that factor must be positive.”"""
    assert good()['intervals'][0]['electricity_kWh']>0
@pytest.mark.heat_pump
def test_zero_command_has_no_plant_energy_and_null_interval_cop():
    """“At zero command, interval heat/electricity are zero and COP is `null`.”"""
    a=case(); a['segments']=[dict(a['segments'][0],heat_command=0)]; x=good(a)['intervals'][0]; assert x['heat_delivered_kWh']==0 and x['electricity_kWh']==0 and x['cop'] is None
@pytest.mark.heat_pump
def test_extreme_cold_capacity_floor_does_not_create_negative_heat():
    """“Available heat is `Q_nominal_W * max(0, 1 + capacity_slope_per_K*(T_outdoor_C-capacity_reference_C))`, and delivered heat is available heat times command `y`.”"""
    a=case(); a['segments'][0]['T_outdoor_C']=-100; assert good(a)['intervals'][0]['heat_delivered_kWh']==0
@pytest.mark.heat_pump
def test_watt_seconds_and_seasonal_cop_use_energy_not_mean_interval_cop():
    """“`seasonal_cop` (total delivered heat divided by total electricity, or `null` when electricity is zero).”"""
    x=good(); assert x['summary']['seasonal_cop']==pytest.approx(x['summary']['heat_delivered_kWh']/x['summary']['electricity_kWh'])
@pytest.mark.state_accounting
def test_output_schema_order_and_node_identity_follow_input():
    """“The UTF-8 JSON output has exactly `intervals` and `summary`.”"""
    x=good(); assert list(x)==['intervals','summary'] and [n['id'] for n in x['intervals'][0]['nodes']]==['wall','core']; assert set(x['intervals'][0]['nodes'][0])=={'id','end_C','stored_energy_kWh','phase_fraction'}

@pytest.mark.state_accounting
def test_zero_forcing_preserves_constitutive_energy_and_phase_fraction():
    """“`stored_energy_kWh` is the constitutive stored energy relative to 0 C, converted to kWh.”"""
    a=case(); a['building']['links']=[]
    for n in a['building']['nodes']:
        n.update(G_out_W_per_K=0.0, area_m2=0.0)
    a['segments']=[{'duration_s':1.0,'T_outdoor_C':16.0,'T_radiant_C':16.0,'T_supply_C':35.0,'heat_command':0.0,'gains_W_by_node':[0.0,0.0]}]
    x=good(a); w=x['intervals'][0]['nodes'][0]; expected=(900000*16+1200000/2*(1+math.tanh((16-18)/1.5)))/3.6e6; frac=0.5*(1+math.tanh((16-18)/1.5))
    assert w['end_C']==pytest.approx(16.0,abs=2e-7); assert w['stored_energy_kWh']==pytest.approx(expected,rel=1e-9,abs=1e-12); assert w['phase_fraction']==pytest.approx(frac,rel=1e-12,abs=1e-12); assert x['summary']['latent_storage_kWh']==pytest.approx(1200000*frac/3.6e6,rel=1e-9,abs=1e-12)
@pytest.mark.state_accounting
def test_node_extrema_include_initial_state_and_each_reported_endpoint():
    """“`node_extrema` mapping every node ID to `min_C` and `max_C` over its initial value and interval endpoints.”"""
    assert good()['summary']['node_extrema']['wall']['min_C']<=16
@pytest.mark.state_accounting
def test_splitting_a_constant_operating_interval_preserves_final_state_and_totals():
    """“Node state carries continuously between segments.”"""
    a=case(); s=a['segments'][0]; a['segments']=[dict(s,duration_s=900)]; b=copy.deepcopy(a); b['segments']=[dict(s,duration_s=450),dict(s,duration_s=450)]; assert good(a)['summary']['heat_delivered_kWh']==pytest.approx(good(b)['summary']['heat_delivered_kWh'])
@pytest.mark.state_accounting
def test_summary_energy_fields_equal_interval_sums():
    """“The summary additionally contains sums of each interval energy/exchange/residual, `seasonal_cop` (total delivered heat divided by total electricity, or `null` when electricity is zero), and `node_extrema` mapping every node ID to `min_C` and `max_C` over its initial value and interval endpoints.”"""
    x=good()
    for k in ['heat_delivered_kWh','electricity_kWh','outdoor_exchange_kWh','radiant_exchange_kWh','building_gains_kWh','thermal_balance_residual_kWh']:
        assert x['summary'][k]==pytest.approx(sum(r[k] for r in x['intervals']))
@pytest.mark.invalid_input
@pytest.mark.parametrize('mut',range(14))
def test_invalid_network_or_operating_record_rejects_without_file_side_effects(mut):
    """“Invalid schemas, node properties, material parameters, links, heat allocations, operating conditions, or daily horizons exit nonzero and must not create or alter `OUTPUT.json`.”"""
    # The command must also accept a complete valid record; a starter that
    # rejects every input must not earn the rejection-group weight.
    assert run(case())[0].returncode == 0
    a=case(); actions=[lambda: a['building']['nodes'][0].pop('area_m2'),lambda: a['building']['nodes'][0].update(latent_heat_J=-1),lambda: a['building']['nodes'][0].update(transition_width_K=0),lambda: a['building']['nodes'][0].update(heat_fraction=.2),lambda: a['building']['links'][0].update(G_W_per_K=0),lambda: a['building']['links'].append({'a':'core','b':'wall','G_W_per_K':2}),lambda: a['segments'][0].update(gains_W_by_node=[0]),lambda: a['segments'][0].update(heat_command=2),lambda: a['segments'][0].update(duration_s=0),lambda: a['segments'][0].update(T_supply_C=-300),lambda: a['heat_pump'].update(COP_nominal=1),lambda: a['building'].update(sigma_W_per_m2_K4=0),lambda: a['segments'][0].update(duration_s=86400),lambda: a['segments'][0].update(heat_command=float('nan'))]
    actions[mut]()
    r,b,s,tmp,side=run(a)
    assert r.returncode != 0
    assert b is None
    assert not tmp
    assert not side['report'] and not side['journal'] and not side['summary']
    assert not side['output']
    r,b,s,tmp,side=run(a,True)
    assert r.returncode != 0
    assert b == s
    assert not tmp
    assert side['output']
    assert not side['report'] and not side['journal'] and not side['summary']
@pytest.mark.invalid_input
def test_late_invalid_segment_does_not_publish_valid_prefix():
    """“The output may be published only when validation and the complete report have succeeded.”"""
    assert run(case())[0].returncode == 0
    a=case(); a['segments'][1]['duration_s']=0
    r,b,s,tmp,side=run(a,True)
    assert r.returncode != 0
    assert b == s
    assert not tmp
    assert side['output']
    assert not side['report'] and not side['journal'] and not side['summary']
@pytest.mark.invalid_input
def test_daily_horizon_limit_is_applied_to_complete_record():
    """“a record has 1 to 96 segments spanning no more than 86,400 seconds.”"""
    assert run(case())[0].returncode == 0
    a=case(); a['segments'][0]['duration_s']=50000; a['segments'][1]['duration_s']=36401
    r,b,s,tmp,side=run(a)
    assert r.returncode != 0
    assert b is None
    assert not tmp
    assert not side['report'] and not side['journal'] and not side['summary']
    assert not side['output']
