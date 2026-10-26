"""Generate the NWI Mesh Home Assistant dashboards.

  python build_dashboards.py            -> writes ../dashboards/*.yaml

Two flavours from one definition:
  nwimesh-stock.yaml  built-in cards only (works on any HA)
  nwimesh-pro.yaml    + card-mod and mini-graph-card (HACS) for glow/animation
"""
import os
import sys
import yaml

GREEN = '#67ea94'      # Meshtastic green
TEAL = '#2dd4bf'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dashboards')

E = {
    'health': 'sensor.nwi_mesh_health',
    'active': 'sensor.nwi_mesh_active_nodes',
    'known': 'sensor.nwi_mesh_known_nodes',
    'new_day': 'sensor.nwi_mesh_new_nodes_today',
    'new_week': 'sensor.nwi_mesh_new_nodes_this_week',
    'gateways': 'sensor.nwi_mesh_gateways',
    'packets': 'sensor.nwi_mesh_packets_today',
    'rate': 'sensor.nwi_mesh_packet_rate',
    'util': 'sensor.nwi_mesh_channel_utilization',
    'delivery': 'sensor.nwi_mesh_delivery_ratio',
    'relayed': 'sensor.nwi_mesh_relayed_share',
    'msgs': 'sensor.nwi_mesh_messages_today',
    'pki': 'sensor.nwi_mesh_encrypted_nodes',
    'anomalies': 'sensor.nwi_mesh_anomaly_flags',
    'brokers_up': 'sensor.nwi_mesh_mqtt_brokers_up',
    'broker': 'binary_sensor.nwi_mesh_broker',
    'online': 'binary_sensor.nwi_mesh_online',
    'last_msg': 'sensor.nwi_mesh_last_message',
    'heard': 'sensor.nwi_mesh_messages_heard',
    'named': 'sensor.nwi_mesh_nodes_named',
    'mqtt': 'binary_sensor.nwi_mesh_mqtt_connected',
}

# ---------------------------------------------------------------- styles
GLASS = f"""ha-card {{
  background: linear-gradient(150deg, rgba(103,234,148,.10), rgba(45,212,191,.03) 60%, rgba(255,255,255,.01));
  border: 1px solid rgba(103,234,148,.22);
  box-shadow: 0 0 22px rgba(103,234,148,.08), inset 0 1px 0 rgba(255,255,255,.05);
  backdrop-filter: blur(6px);
  transition: box-shadow .3s, transform .3s;
}}
ha-card:hover {{ box-shadow: 0 0 28px rgba(103,234,148,.25); transform: translateY(-2px); }}
"""

# health-aware glow: green when healthy, amber when degraded, red when poor
HEALTH_GLOW = GLASS + f"""{{% set h = states('{E['health']}') | int(0) %}}
{{% set c = '103,234,148' if h >= 70 else ('251,191,36' if h >= 50 else '248,113,113') %}}
ha-card {{
  border-color: rgba({{{{ c }}}},.45);
  --primary-text-color: rgb({{{{ c }}}});
  animation: nwm-breathe 4s ease-in-out infinite;
}}
@keyframes nwm-breathe {{
  0%,100% {{ box-shadow: 0 0 14px rgba({{{{ c }}}},.15); }}
  50%     {{ box-shadow: 0 0 34px rgba({{{{ c }}}},.45); }}
}}
"""

HERO_CARD = f"""ha-card {{
  position: relative; overflow: hidden !important;
  min-height: 150px; padding: 8px 12px;
  color: #eafff2;
  background:
    radial-gradient(circle at 88% 50%, rgba(103,234,148,.28), transparent 35%),
    linear-gradient(115deg, #031a14, #0b3d2e, #06303f, #031a14);
  background-size: 100% 100%, 300% 300%;
  animation: nwm-shift 20s ease infinite;
  border: 1px solid rgba(103,234,148,.35);
  box-shadow: 0 0 40px rgba(103,234,148,.15);
}}
ha-card::before, ha-card::after {{
  content: ''; position: absolute; pointer-events: none;
  right: calc(6% + 2px); top: 50%;
  width: 44px; height: 44px; margin-top: -22px;
  border-radius: 50%; border: 2px solid {GREEN};
  animation: nwm-ping 3.2s cubic-bezier(0,.45,.55,1) infinite;
}}
ha-card::after {{ animation-delay: 1.6s; }}
@keyframes nwm-ping {{
  0%   {{ transform: scale(1);  opacity: .9; }}
  100% {{ transform: scale(4);  opacity: 0;  }}
}}
@keyframes nwm-shift {{
  0%,100% {{ background-position: 0 0, 0% 50%; }}
  50%     {{ background-position: 0 0, 100% 50%; }}
}}
"""

HERO_MD = f""":host {{ overflow: visible !important; }}
h1 {{
  font-size: 2.3em; font-weight: 800; letter-spacing: -.02em;
  margin: 4px 0 6px; line-height: 1.1;
  background: linear-gradient(90deg, #ffffff, {GREEN} 60%, {TEAL});
  -webkit-background-clip: text; background-clip: text; color: transparent;
}}
p {{ margin: 4px 0; padding-right: 96px; font-size: 1.05em; }}
strong {{ color: {GREEN}; }}
sub {{ opacity: .7; letter-spacing: .04em; }}
ha-icon {{
  position: absolute; right: 6%; top: 50%; transform: translateY(-50%);
  --mdc-icon-size: 48px; color: {GREEN};
  filter: drop-shadow(0 0 10px rgba(103,234,148,.8));
}}
"""


def mod(card, style, md=None):
    """Attach a card-mod style (pro only; stripped for stock)."""
    s = {'.': style} if md else style
    if md:
        s['ha-markdown$'] = md
    card['card_mod'] = {'style': s}
    return card


# ---------------------------------------------------------------- cards
def hero():
    h = E['health']
    return {
        'type': 'markdown',
        'grid_options': {'columns': 'full', 'rows': 'auto'},
        'content': (
            "<ha-icon icon=\"mdi:radio-tower\"></ha-icon>\n\n"
            "# NWI Mesh\n"
            f"**{{{{ states('{E['active']}') }}}}** nodes heard in the last 24 h · "
            f"**{{{{ states('{E['gateways']}') }}}}** gateways · "
            f"health **{{{{ states('{h}') }}}}** {{{{ state_attr('{h}', 'label') or '' }}}}\n\n"
            "<sub>LAKE · PORTER · LAPORTE  —  MESHTASTIC LONGFAST · US 915 MHz</sub>"
        ),
    }


def gauge():
    return {
        'type': 'gauge',
        'entity': E['health'],
        'name': 'Mesh health',
        'min': 0, 'max': 100, 'needle': True,
        'segments': [
            {'from': 0, 'color': '#f87171'},
            {'from': 50, 'color': '#fbbf24'},
            {'from': 70, 'color': GREEN},
        ],
        'grid_options': {'columns': 'full', 'rows': 'auto'},
    }


def subscore(attr, name, icon):
    return {
        'type': 'tile', 'entity': E['health'], 'name': name, 'icon': icon,
        'color': 'green', 'vertical': True, 'hide_state': False,
        'state_content': attr,
        'grid_options': {'columns': 6, 'rows': 2},
    }


def stat(key, name, color='green', icon=None, cols=6):
    c = {'type': 'tile', 'entity': E[key], 'name': name, 'color': color,
         'vertical': True, 'grid_options': {'columns': cols, 'rows': 2}}
    if icon:
        c['icon'] = icon
    return c


def mini(key, name, hours, color, thresholds=None, pph=1, fmt=0):
    c = {
        'type': 'custom:mini-graph-card',
        'entities': [{'entity': E[key], 'name': name}],
        'hours_to_show': hours, 'points_per_hour': pph,
        'line_color': color, 'line_width': 3,
        'smoothing': True, 'animate': True, 'decimals': fmt,
        'show': {'fill': 'fade', 'extrema': False, 'labels': False},
        'height': 110,
        'grid_options': {'columns': 16},
    }
    if thresholds:
        c['color_thresholds'] = thresholds
        c['color_thresholds_transition'] = 'smooth'
    return c


def stat_graph(key, name, days):
    return {
        'type': 'statistics-graph', 'title': name, 'entities': [E[key]],
        'days_to_show': days, 'period': 'hour', 'chart_type': 'line',
        'stat_types': ['mean'], 'hide_legend': True,
        'grid_options': {'columns': 16},
    }


JOIN = {
    'type': 'markdown',
    'title': 'Join the mesh',
    'grid_options': {'columns': 'full'},
    'content': (
        "Grab a Meshtastic radio, flash it at "
        "[flasher.meshtastic.org](https://flasher.meshtastic.org), and set:\n\n"
        "| Setting | Value |\n|---|---|\n"
        "| Region | **US** (915 MHz) |\n"
        "| Preset | **LongFast** |\n"
        "| Hop limit | **7** |\n"
        "| Primary channel key | **AQ==** (default) |\n"
        "| MQTT root | **msh/US/IN/NWI** |\n\n"
        "Starter guide: [nwimesh.net/faq](https://nwimesh.net/faq) · "
        "Live map: [hopwatch.nwimesh.net](https://hopwatch.nwimesh.net) · "
        "[Discord](https://discord.gg/4wQ5SWPBfQ)"
    ),
}


def heading(text, icon, badges=None):
    c = {'type': 'heading', 'heading': text, 'icon': icon}
    if badges:
        c['badges'] = badges
    return c


def build(pro):
    hero_c = hero()
    gauge_c = gauge()
    subs = [
        subscore('delivery_ratio', 'Delivery', 'mdi:email-check'),
        subscore('gateway_coverage', 'Coverage', 'mdi:access-point-network'),
        subscore('utilization', 'Airtime', 'mdi:sine-wave'),
        subscore('active_node_trend', 'Node trend', 'mdi:trending-up'),
    ]
    stats = [
        stat('active', 'Active 24 h', 'green', 'mdi:radio-tower'),
        stat('known', 'Known nodes', 'teal'),
        stat('new_day', 'New today', 'light-green'),
        stat('new_week', 'New this week', 'light-green'),
        stat('gateways', 'Gateways', 'cyan'),
        stat('msgs', 'Messages today', 'blue'),
        stat('relayed', 'Relayed', 'indigo'),
        stat('pki', 'Encrypted (PKI)', 'purple'),
    ]
    if pro:
        graphs = [
            mini('active', 'Active nodes · 7 days', 168, GREEN, pph=0.5),
            mini('rate', 'Packets / hour', 48, TEAL),
            mini('util', 'Channel utilization', 48, GREEN, fmt=1, thresholds=[
                {'value': 0, 'color': GREEN},
                {'value': 15, 'color': '#fbbf24'},
                {'value': 25, 'color': '#f87171'},
            ]),
        ]
        mod(hero_c, HERO_CARD, HERO_MD)
        mod(gauge_c, HEALTH_GLOW)
        for c in subs + stats + graphs:
            mod(c, GLASS)
    else:
        graphs = [
            stat_graph('active', 'Active nodes · 7 days', 7),
            stat_graph('rate', 'Packets / hour', 2),
            stat_graph('util', 'Channel utilization', 2),
        ]

    status = [
        {'type': 'tile', 'entity': E['broker'], 'name': 'NWIMesh MQTT broker',
         'icon': 'mdi:server-network', 'color': 'green', 'grid_options': {'columns': 12}},
        {'type': 'tile', 'entity': E['online'], 'name': 'HopWatch API',
         'icon': 'mdi:api', 'color': 'green', 'grid_options': {'columns': 12}},
        {'type': 'tile', 'entity': E['brokers_up'], 'name': 'MQTT brokers up',
         'icon': 'mdi:server-network', 'color': 'teal', 'grid_options': {'columns': 12}},
        {'type': 'tile', 'entity': E['anomalies'], 'name': 'Open anomaly flags',
         'icon': 'mdi:alert-decagram', 'color': 'amber', 'grid_options': {'columns': 12}},
        {'type': 'tile', 'entity': E['packets'], 'name': 'Packets today',
         'icon': 'mdi:swap-vertical-bold', 'color': 'teal', 'grid_options': {'columns': 12}},
        {'type': 'tile', 'entity': E['delivery'], 'name': 'Delivery ratio',
         'icon': 'mdi:check-network', 'color': 'green', 'grid_options': {'columns': 12}},
    ]
    join = dict(JOIN)
    if pro:
        for c in status:
            mod(c, GLASS)
        mod(join, GLASS)

    sections = [
        {'type': 'grid', 'column_span': 4, 'cards': [hero_c]},
        {'type': 'grid', 'column_span': 2, 'cards': [
            heading('Mesh health', 'mdi:heart-pulse'), gauge_c, *subs]},
        {'type': 'grid', 'column_span': 2, 'cards': [
            heading('Network', 'mdi:lan'), *stats]},
        {'type': 'grid', 'column_span': 4, 'cards': [
            heading('Trends', 'mdi:chart-bell-curve-cumulative'), *graphs]},
        {'type': 'grid', 'column_span': 2, 'cards': [
            heading('Infrastructure', 'mdi:server'), *status]},
        {'type': 'grid', 'column_span': 2, 'cards': [join]},
    ]
    return {
        'title': 'NWI Mesh',
        'views': [{
            'title': 'Network', 'path': 'nwi-mesh',
            'type': 'sections', 'max_columns': 4, 'dense_section_placement': True,
            'sections': sections,
        }, messages_view(pro)],
    }


FEED = f"""{{% set msgs = state_attr('{E['last_msg']}', 'recent') or [] %}}
{{% if msgs | count == 0 %}}
*Listening… public channel messages show up here as the mesh hears them.*
{{% endif %}}
{{% for m in msgs %}}
{{% set hops = 'direct' if m.hops == 0 else (m.hops ~ ' hop' ~ ('s' if m.hops != 1 else '')) if m.hops is not none else '' %}}
{{% set text = m.text | replace('&', '&amp;') | replace('<', '&lt;') | replace('>', '&gt;') | replace('\\n', ' ') %}}
**{{{{ m.long_name | replace('<', '&lt;') }}}}** <sub>{{{{ m.short_name | replace('<', '&lt;') }}}} · {{{{ relative_time(as_datetime(m.time)) }}}} ago · {{{{ m.channel }}}}{{{{ ' · ' ~ hops if hops }}}}{{{{ ' · SNR ' ~ m.snr if m.snr is not none }}}}</sub>
> {{{{ text }}}}

{{% endfor %}}"""

FEED_MD = f"""blockquote {{
  margin: 4px 0 16px; padding: 10px 14px;
  border: none; border-left: 3px solid {GREEN};
  border-radius: 4px 16px 16px 16px;
  background: linear-gradient(135deg, rgba(103,234,148,.16), rgba(45,212,191,.06));
  font-size: 1.05em; line-height: 1.4;
}}
strong {{ color: {GREEN}; }}
sub {{ opacity: .65; margin-left: 4px; }}
"""


def messages_view(pro):
    feed = {'type': 'markdown', 'title': 'Mesh chat', 'content': FEED,
            'grid_options': {'columns': 'full'}}
    side = [
        {'type': 'tile', 'entity': E['mqtt'], 'name': 'Listening on MQTT',
         'icon': 'mdi:lan-connect', 'color': 'green', 'grid_options': {'columns': 'full'}},
        stat('heard', 'Messages heard', 'green', 'mdi:message-badge', cols=6),
        stat('named', 'Nodes named', 'teal', 'mdi:card-account-details', cols=6),
        stat('msgs', 'Mesh-wide today', 'blue', 'mdi:message-text', cols=6),
        stat('active', 'Active 24 h', 'green', 'mdi:radio-tower', cols=6),
        {'type': 'markdown', 'grid_options': {'columns': 'full'}, 'content': (
            "Only the public channels you configured are decoded (LongFast by default). "
            "Direct messages and private channels stay encrypted.\n\n"
            "**Automate it:** trigger on `event.nwi_mesh_message` or the "
            "`nwimesh_message` event to get a phone alert for keywords or nodes.")},
    ]
    if pro:
        mod(feed, GLASS, FEED_MD)
        for c in side:
            mod(c, GLASS)
    return {
        'title': 'Messages', 'path': 'messages',
        'type': 'sections', 'max_columns': 3,
        'sections': [
            {'type': 'grid', 'column_span': 2, 'cards': [feed]},
            {'type': 'grid', 'column_span': 1, 'cards': [heading('Live feed', 'mdi:access-point'), *side]},
        ],
    }


class Dumper(yaml.SafeDumper):
    pass


def _str(d, s):
    return d.represent_scalar('tag:yaml.org,2002:str', s, style='|' if '\n' in s else None)


Dumper.add_representer(str, _str)

HEADER = """# NWI Mesh dashboard ({flavour}) - https://nwimesh.net
# Requires the NWI Mesh integration (custom_components/nwimesh).
{req}# Install: Settings > Dashboards > Add dashboard > New dashboard from scratch,
#          open it, ⋮ > Edit dashboard > ⋮ > Raw configuration editor, paste this file.
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for pro, name, req in (
        (False, 'nwimesh-stock.yaml', '# Built-in cards only - no HACS needed.\n'),
        (True, 'nwimesh-pro.yaml', '# Needs HACS frontend plugins: card-mod, mini-graph-card.\n'),
    ):
        cfg = build(pro)
        body = yaml.dump(cfg, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=1000)
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            f.write(HEADER.format(flavour='pro' if pro else 'stock', req=req) + body)
        print('wrote', name)
    if '--json' in sys.argv:
        import json
        json.dump(build(True), sys.stdout)


if __name__ == '__main__':
    main()
