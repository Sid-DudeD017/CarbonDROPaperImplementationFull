import json
from pathlib import Path

def build_html():
    project_dir = Path(__file__).resolve().parent.parent

    with open(project_dir / 'website/data/results.json') as f:
        data = json.load(f)

    with open(project_dir / 'website/template.html') as f:
        template = f.read()

    metrics = data['metrics']
    config = data['configuration']
    prov = data['provenance_classifications']

    replacements = {
        '{{SEED}}': str(config['seed']),
        '{{INPUT_FILE}}': config['input_file'],
        '{{T_SLOTS}}': str(config['T']),
        '{{J_JOBS}}': str(config['J']),
        '{{S_SCENARIOS}}': str(config['S']),
        '{{OOD_CASES}}': str(config['n_ood']),
        '{{PROV_CAISO_CARBON}}': prov['caiso_north_carbon_rate'],
        '{{PROV_CAISO_PRICE}}': prov['caiso_north_nodal_prices'],
        '{{PROV_ADDITIONAL_SITES}}': prov['additional_cloud_sites'],
        '{{PROV_RENEWABLE_PROXY}}': prov['renewable_availability_proxy'],
        '{{PROV_WORKLOAD_TRACES}}': prov['workload_traces'],
        '{{PROV_OOD_SCENARIOS}}': prov['ood_scenarios'],
        '{{PROV_CARBON_CVAR09}}': prov['carbon_cvar09'],
        '{{TIMESTAMP}}': "Generated reproducibly",
        '{{COMMIT}}': data['source_commit'],

        '{{CM_COST}}': f"{metrics['CM']['exp_cost']:.6f}",
        '{{CM_CVAR}}': f"{metrics['CM']['cvar90_carbon']:.2f}",
        '{{CF_CARBON_RED_PCT}}': f"{metrics['CF']['reduction_carbon_vs_cm_pct']:.2f}",
        '{{RF_CARBON}}': f"{metrics['RF']['exp_carbon']:.2f}",
        '{{RF_CARBON_RED_PCT}}': f"{metrics['RF']['reduction_carbon_vs_cm_pct']:.2f}",
        '{{SBS_CARBON_RED_PCT}}': f"{metrics['SBS']['reduction_carbon_vs_cm_pct']:.2f}",
        '{{SBS_CVAR_RED_PCT}}': f"{metrics['SBS']['reduction_cvar_vs_cm_pct']:.2f}",
        '{{RO_CVAR}}': f"{metrics['RO']['cvar90_carbon']:.2f}",
        '{{RO_CVAR_RED_PCT}}': f"{metrics['RO']['reduction_cvar_vs_cm_pct']:.2f}",
        '{{DRO_CARBON_RED_PCT}}': f"{metrics['DRO']['reduction_carbon_vs_cm_pct']:.2f}",
        '{{DRO_CVAR_RED_PCT}}': f"{metrics['DRO']['reduction_cvar_vs_cm_pct']:.2f}",
    }

    for k, v in replacements.items():
        template = template.replace(k, v)

    results_html = []
    order = ['CM', 'CF', 'RF', 'SBS', 'RO', 'DRO']
    for method in order:
        m = metrics[method]
        color = "text-secondary" if method == "CM" else "text-primary" if method in ["CF", "RF"] else "text-on-surface" if method == "SBS" else "text-tertiary"
        results_html.append(f'''
<tr class="bg-surface-container-low hover:bg-surface-container">
<td class="py-space-sm px-space-sm font-semibold {color}">{method}</td>
<td class="py-space-sm px-space-sm text-right font-medium {color}">{m['exp_cost']:.6f}</td>
<td class="py-space-sm px-space-sm text-right">{m['exp_carbon']:.6f}</td>
<td class="py-space-sm px-space-sm text-right">{m['cvar90_carbon']:.6f}</td>
<td class="py-space-sm px-space-sm text-center text-primary font-bold">{int(m['sla_violation_rate'])}</td>
</tr>
''')
    template = template.replace('{{RESULTS_TABLE_ROWS}}', ''.join(results_html))

    paper_carbon_html = []
    for method in ['CF', 'RF', 'SBS', 'RO', 'DRO']:
        m = metrics[method]['paper_comparison']
        proj_val = metrics[method]['reduction_carbon_vs_cm_pct']
        proj = f"{proj_val:.2f}%" if proj_val is not None else "Not reported"
        pap = f"{m['paper_carbon_reduction_vs_cm_pct']:.2f}%" if m['paper_carbon_reduction_vs_cm_pct'] is not None else "Not reported"
        paper_carbon_html.append(f'''
<tr>
<td class="py-space-xs px-space-sm font-semibold">{method}</td>
<td class="py-space-xs px-space-sm text-right text-primary">{proj}</td>
<td class="py-space-xs px-space-sm text-right text-on-surface-variant">{pap}</td>
</tr>
''')
    template = template.replace('{{PAPER_CARBON_ROWS}}', ''.join(paper_carbon_html))

    paper_cvar_html = []
    for method in ['CF', 'RF', 'SBS', 'RO', 'DRO']:
        m = metrics[method]['paper_comparison']
        proj_val = metrics[method]['reduction_cvar_vs_cm_pct']
        proj = f"{proj_val:.2f}%" if proj_val is not None else "Not reported"
        pap = f"{m['paper_cvar_reduction_vs_cm_pct']:.2f}%" if m['paper_cvar_reduction_vs_cm_pct'] is not None else "Not reported"
        paper_cvar_html.append(f'''
<tr>
<td class="py-space-xs px-space-sm font-semibold">{method}</td>
<td class="py-space-xs px-space-sm text-right text-tertiary">{proj}</td>
<td class="py-space-xs px-space-sm text-right text-on-surface-variant">{pap}</td>
</tr>
''')
    template = template.replace('{{PAPER_CVAR_ROWS}}', ''.join(paper_cvar_html))

    out_path = project_dir / 'website/index.html'
    with open(out_path, 'w') as f:
        f.write(template)

if __name__ == '__main__':
    build_html()
