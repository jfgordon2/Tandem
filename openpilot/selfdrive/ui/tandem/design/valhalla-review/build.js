// Build approval drafts from the current Valhalla UI diff. Does not edit application code or approved mocks.
const fs = require('fs');
const path = require('path');
const D = path.resolve(__dirname, '..');
const states = [];
const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const read = name => fs.readFileSync(path.join(D, name + '.html'), 'utf8');
function replace(text, from, to) {
  if (!text.includes(from)) throw new Error('Missing template fragment: ' + from.slice(0, 90));
  return text.replace(from, to);
}
const fonts = [400, 500, 600, 700, 800].map((weight, i) =>
  `@font-face{font-family:Figtree;font-weight:${weight};src:url('../../../assets/fonts/Figtree-${['Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold'][i]}.ttf')}`).join('');
const css = `${fonts}*{box-sizing:border-box}body{margin:0;background:#000;color:#F2F5F9;font-family:Figtree,system-ui,sans-serif}button,input{font-family:inherit}button{cursor:default}button:disabled{color:#8FA0B5!important;background:#23272E!important}.row{height:70px;flex-shrink:0;padding:0 22px;display:flex;align-items:center;gap:14px;border-top:1px solid #23272E}.words{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}.label{font-size:18px;font-weight:600}.sub{font-size:14px;color:#AEB6C2}.btn{height:44px;border:0;border-radius:12px;padding:0 18px;font-size:15px;font-weight:600;color:#F2F5F9;background:#23272E}.panel{background:#16191D;border-radius:22px;overflow:hidden}.page{width:1125px;height:563px;display:flex;flex-direction:column;overflow:hidden}.panelhead{padding:17px 22px 13px}.panelhead h2{font-size:24px;margin:0 0 4px;font-weight:700}.footer{height:102px;flex-shrink:0;border-top:1px solid #1F242B;background:#0E1013;display:flex;align-items:center;gap:20px;padding:0 16px}.footer .note{flex:1;min-width:0;font-size:16px;color:#8FA0B5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.back{width:74px;height:74px;flex-shrink:0;border:0;border-radius:18px;background:#1F2328;display:flex;align-items:center;justify-content:center;color:#F2F5F9}.danger{color:#F4AFB7;background:#3A1D24}.disabled .label,.disabled .sub{color:#8FA0B5}.disabled .btn{color:#8FA0B5;background:#23272E}.disabled .switch{opacity:.45}.kfield{height:56px;display:flex;align-items:center;gap:12px;border:2px solid #5AAAF8;border-radius:14px;background:#1A1D22;padding:0 16px;font-size:20px}.searchtop{height:206px;flex-shrink:0;padding:14px 16px 10px;display:flex;flex-direction:column;gap:10px}.searchbar{display:flex;gap:10px;height:56px;flex-shrink:0}.smallback{width:56px;height:56px;border-radius:14px}.cardgrid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:8px;flex:1;min-height:0}.resultcard{display:flex;align-items:center;gap:12px;padding:0 16px;background:#16191D;border-radius:14px;min-width:0}.resultcard strong{font-size:17px;font-weight:600}.resultcard small{font-size:13px;color:#AEB6C2}.resultcard .words{overflow:hidden}.resultcard span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}`;
const svg = (body, size=24, color='#F2F5F9') => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const back = svg('<path d="M15 5l-7 7 7 7"/>', 28);
const chevron = svg('<path d="M9 5l7 7-7 7"/>', 18, '#7DBBF9');
const searchIcon = svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>', 22, '#AEB6C2');
const button = (label, disabled=false, danger=false) => `<button class="btn${danger ? ' danger' : ''}"${disabled ? ' disabled' : ''}>${esc(label)}</button>`;
const row = (title, subtitle, control, disabled=false) => `<div class="row${disabled ? ' disabled' : ''}"><div class="words"><span class="label">${esc(title)}</span><span class="sub">${esc(subtitle)}</span></div>${control}</div>`;
const toggle = (on, disabled=false) => `<div class="switch" role="switch" aria-checked="${on}" aria-disabled="${disabled}" style="width:72px;height:42px;flex-shrink:0;border-radius:21px;background:${on ? '#5AAAF8' : '#2A2F36'};padding:4px;display:flex;justify-content:${on ? 'flex-end' : 'flex-start'}"><span style="width:34px;height:34px;border-radius:50%;background:${on ? '#0E1520' : '#AEB6C2'}"></span></div>`;
const footer = (note, action='') => `<div class="footer"><button class="back">${back}</button><span class="note">${esc(note)}</span>${action}</div>`;
function page(title, body) { return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${css}</style></head><body>${body}</body></html>\n`; }
function add(id, group, title, when, change, html, extra={}) {
  const file = 'valhalla-' + id;
  // Use local copies of the shipped fonts; review must work without a data connection.
  html = html.replaceAll(/<link[^>]*href="https:\/\/fonts[^>]*>/g, '').replace('</head>', `<style>${fonts}</style></head>`);
  fs.writeFileSync(path.join(D, file + '.html'), html);
  states.push({id, file, group, title, when, change, approval:'pending', ...extra});
}

// Navigation settings. The new row is present even with local routing turned off.
function nav(local, keys, scrolled) {
  const mapboxRow=row('Mapbox Keys', local ? 'Optional for online search and speed-limit filling' : keys ? 'Added' : 'Not added · needed for place search and routes',
    button(keys ? 'How to change' : 'How to add')).replace('<span class="sub">', `<span class="sub" style="color:${keys?'#6FD8A0':'#F0B35A'}">`);
  const content = row('Home', '12 Elm St', button('Change')) + row('Work', 'Not set', button('Set')) +
    row('Other favorites', '1 saved', chevron) + row('End Route When Parked', 'Clears the destination when you turn off the car', toggle(true)) +
    row('Offline routes', 'Saved places and rerouting without a connection', button('Manage')) +
    mapboxRow + row('Offline Maps', 'Speed limits and street names without a connection', chevron);
  const side = `<aside style="width:300px;flex-shrink:0;display:flex;flex-direction:column;gap:6px;padding-top:8px"><span style="font-size:14px;font-weight:700;letter-spacing:1.8px;color:#7DBBF9;padding:0 16px 8px">SPEED &amp; STEERING</span>${['Everyday','Vehicle Profile','Weather','Navigation'].map(t=>`<div style="height:56px;border-radius:14px;padding:0 16px;display:flex;align-items:center;font-size:18px;font-weight:600;background:${t==='Navigation'?'#1F2E45':'transparent'}">${t}</div>`).join('')}<div style="flex:1"></div><button class="btn" style="height:44px">Tuner Mode ›</button></aside>`;
  return page('Navigation settings', `<div class="page"><div style="flex:1;min-height:0;display:flex;gap:18px;padding:18px 20px 14px">${side}<div class="panel" style="flex:1;min-width:0;display:flex;flex-direction:column"><div class="panelhead"><h2>Navigation</h2><div class="sub">While a route is active, the car slows for turns and uses route speed limits</div></div><div style="overflow-y:auto;flex:1;min-height:0" id="navrows"><div>${content}</div></div></div></div><div class="footer"><button class="back">${back}</button><div style="display:flex;flex:1;gap:6px">${['Driving','Device','Connections','Software'].map(t=>`<div style="flex:1;height:74px;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700;border-radius:18px;background:${t==='Driving'?'#5AAAF8':'transparent'};color:${t==='Driving'?'#0B1A2B':'#C9D0DA'}">${t}</div>`).join('')}</div></div></div>${scrolled ? '<script>document.getElementById("navrows").scrollTop=1000;</script>' : ''}`);
}
add('nav-entry','settings','Navigation entry point','Open Tandem Settings › Driving › Speed & Steering › Navigation, with offline routing either on or off.','Adds the Offline routes / Manage row below End Route When Parked. Standard rows scroll.',nav(false,false,false));
add('nav-online','settings','Navigation, offline routing off','Scroll down in Navigation with offline routing off and no Mapbox keys.','The new Manage row is still available; Offline Maps now explicitly describes speed limits and street names.',nav(false,false,true));
add('nav-local','settings','Navigation, offline routing on','Scroll down in Navigation while effective offline routing is on; Mapbox keys are absent.','Mapbox keys are described as optional for online search and speed-limit filling.',nav(true,false,true));
add('nav-local-keys','settings','Navigation, keys already saved','Same as above, but both Mapbox keys have been saved.','The helper action says How to change; the saved-keys subtitle uses the existing green treatment.',nav(true,true,true));

// Reuse the approved keyboard's key grid, with only its caller-specific title/field/action changed.
const kbSource = read('keyboard');
const kbTail = kbSource.slice(kbSource.indexOf('  <div role="group"'), kbSource.lastIndexOf('</div>'));
function keyPanel(action, enabled=true) {
  let body=kbTail.replace('>Set up</button>', `>${esc(action)}</button>`);
  if (!enabled) body=body.replace('background: #5AAAF8; color: #0B1A2B;', 'background: #2A2F36; color: #8FA0B5;');
  return body;
}
function searchPage(query, cards, notice='', results=false) {
  const field=`<div class="searchbar"><button class="back smallback">${back}</button><div class="kfield" style="flex:1;min-width:0">${searchIcon}<span style="flex:1;min-width:0;overflow:hidden;white-space:nowrap">${esc(query)}</span>${query ? '<span style="font-size:22px;color:#AEB6C2">×</span>' : ''}</div></div>`;
  const contents=cards.map(([title,where])=>`<div class="resultcard">${chevron}<div class="words"><strong>${esc(title)}</strong><small>${esc(where)}</small></div></div>`).join('');
  if (results) return page('Search results', `<div class="page" style="padding:14px 16px;gap:12px">${field}<div class="panel" style="flex:1">${notice ? `<div style="padding:22px;font-size:15px;color:#AEB6C2">${esc(notice)}</div>` : cards.map(([title,where])=>row(title,where,chevron)).join('')}</div></div>`);
  return page('Search', `<div class="page"><div class="searchtop">${field}${notice ? `<div style="flex:1;display:flex;align-items:center;font-size:15px;color:#F0B35A;padding:0 6px">${esc(notice)}</div>` : `<div class="cardgrid">${contents}</div>`}</div>${keyPanel('Search',query.length>=3)}</div>`);
}
add('search-valhalla','settings','Settings search: Valhalla','Open settings search and type valhalla, offline routes, or another matching term. This works before enabling the feature.','The new Offline routes setting is indexed; selecting it goes to Navigation.',searchPage('valhalla',[['Offline routes','Driving › Speed & Steering › Navigation']]));
add('search-road-data','settings','Settings search: road-data wording','Search for street names and press Search to show all results.','The updated Offline Maps details now match this query in Navigation and Display › Map; details affect matching, while the result displays its location.',searchPage('street names',[['Offline Maps','Driving › Speed & Steering › Navigation'],['Offline Maps','Driving › Display › Map']], '',true));

let saved=read('destinationslocal');
saved=saved.replace('[Home address]','12 Elm St, Des Moines').replace('[Work address]','200 Market St, Des Moines').replaceAll('[Recent place]','Hardware Store').replaceAll('[Street address, city]','100 Market St, Des Moines');
add('places-ready','places','Saved places: data ready','Open Where to? from Home, settings, or the driving bar while offline routing is on and the runtime plus selected bundle pass readiness checks.','The badge says Offline route data ready; the footer opens Offline routes, including when entered from the driving screen.',saved);
const noBadge=saved.replace(/      <span style="display: flex; align-items: center; gap: 8px; height: 44px;[\s\S]*?      <\/span>\n/, '');
add('places-not-ready','places','Saved places: setup/data missing','Open Where to? with offline routing on but no usable runtime, no active bundle, or incompatible data.','The data-ready badge is absent. Offline routes still opens management; selecting a saved place explains the blocking reason in its preview.',noBadge);
const noKeyNotice='Search needs the public Mapbox key · see Settings › Driving › Speed & Steering › Navigation';
add('recent-no-coordinates','places','Name-only old recent: current search fallback','Tap a recent that contains a name but no usable coordinates, with no public Mapbox key.','It opens the existing search screen instead of reusing a previous destination. Current code clears the attempted query and shows the public-key notice; this is an implementation gap, not a proposed new design.',searchPage('',[],noKeyNotice),{finding:'The _pick path sets the query before _go(SEARCH), which clears it. The public-key notice also masks the new missing-coordinate error. This pass does not fix either behavior.'});
add('recent-coordinate-error','places','Name-only recent: added error wording','The controller rejects a saved place without coordinates. This text is stored as the search error and can appear in the full-results view if a new search has not replaced it.','Added error wording: This saved place has no coordinates. Search again when online. The ordinary keyboard path can mask it, as noted in the adjacent state.',searchPage('Old saved place',[],'Search unavailable · This saved place has no coordinates. Search again when online.',true),{finding:'Review the error wording, but do not treat this as proof that the current ordinary tap path displays it reliably.'});

// Preview geometry is illustrative; do not imply downloaded display tiles.
let preview=read('routepreviewlocal').replace('[Destination name]','Hardware Store').replace('[Street address, city]','100 Market St, Des Moines').replace('[ETA]','5:18 PM').replace('[min]','18 min').replace('[mi]','3.3 mi');
preview=preview.replace(/      <g stroke="#253343"[\s\S]*?<\/g>\n/,'');
add('preview-ready','preview','Preview ready','Choose a coordinate-bearing saved place while offline routing is on; the current local preview succeeds.','Uses local route geometry and estimates. Start is enabled; the second note describes the independent road data.',preview);
add('preview-alternative','preview','Saved Mapbox alternative','Preview a saved destination with a routeId beginning alt-.','The old provider-specific alternative is recalculated locally. The second note says Recalculates the saved route locally.',replace(preview,'Road data still supplies speed limits','Recalculates the saved route locally'));
const previewStatuses=[
  ['pending','Finding a route…','A local preview request is in progress, including refresh after its start position, bundle, language or destination changes.'],
  ['no-gps','Needs a GPS fix to plan the route','Neither a usable live GPS position nor a saved parked position is available for the preview.'],
  ['runtime','Set up offline routes in Navigation settings','The dedicated runtime or matching runtime receipt is missing.'],
  ['missing','Download offline routing data','No routing bundle is selected/installed. Existing speed-limit maps alone do not satisfy this check.'],
  ['incompatible','Routing data needs to be installed again','The selected graph/manifest is incompatible, incomplete, or fails verification.'],
  ['coverage','This trip needs more routing data','The route endpoints are outside the selected routing graph coverage precheck.'],
  ['no-route','No offline route found for this trip','The native router cannot find an automobile path for the trip.'],
  ['busy','Routing is busy. Trying again…','The local broker queue is full. The preview retries after its existing delay.'],
  ['timeout','The route took too long. Trying again…','The preview request reaches its finite deadline; a later retry can recover.'],
  ['worker','Routing is unavailable. Trying again…','The broker/native worker is absent, exits, or cannot be reached.'],
  ['invalid-response','Routing returned an unusable route','The normalizer rejects a malformed native result before it can become a preview.'],
  ['invalid-place','This place has no usable coordinates','An invalid coordinate request reaches the provider; ordinary invalid saved picks are redirected to search earlier.'],
  ['updated','Finding the updated route…','A response was superseded by a newer request or routing-data generation.'],
  ['unknown','Routing is unavailable','An unrecognized provider error is mapped to the generic message.'],
];
for (const [id,text,when] of previewStatuses) {
  const html=replace(read('routepreviewmissing'),'Download offline routing data',esc(text)).replace('[Destination name]','Hardware Store').replace('[Street address, city]','100 Market St, Des Moines');
  add('preview-'+id,'preview','Preview: '+id.replaceAll('-',' '),'Offline routing is on. '+when,'The map shows the reason, estimates are empty, and Start is disabled; the existing back and save controls remain.',html);
}

// Driver screen: exact status wording comes from routing_status.py. The rest is the approved onroad mock.
const driveBase=read('onroadnavwaiting').replace('flex:1;min-width:0;font-size:18px',
  'flex:1;min-width:0;font-size:18px;color:#AEB6C2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis');
const driveStates=[
  ['gps','Waiting for a fresh GPS fix','The active route has no usable live GPS fix, or its timestamp is older than 2.5 seconds or in the future.'],
  ['finding','Finding a route…','The first local route is being calculated, so there is not yet a valid instruction/arrival estimate.'],
  ['rerouting','Finding another offline route…','The car is off the route or its bearing disagrees with the route, and a replacement is being calculated.'],
  ['busy','Routing is busy. Trying again…','The broker reports a busy queue while the route has no valid instruction.'],
  ['timeout','The route took too long. Trying again…','The active-route request exceeded its deadline and instructions remain invalid.'],
  ['worker','Routing is unavailable. Trying again…','The routing worker stopped or the status snapshot is absent/stale. The latter defaults to this wording after 2.5 seconds.'],
  ['missing','Download offline routing data','The selected bundle is missing while a destination remains set.'],
  ['runtime','Set up offline routes in Navigation settings','The dedicated runtime/readiness receipt is missing while a destination remains set.'],
  ['incompatible','Routing data needs to be installed again','The active routing package is corrupt or incompatible.'],
  ['coverage','This trip needs more routing data','Local routing reports that the endpoints need more coverage.'],
  ['no-route','No offline route found for this trip','No replacement route can be found and guidance is invalid.'],
  ['invalid-response','Routing returned an unusable route','The route result failed normalization, so guidance is invalid.'],
  ['invalid-place','This place has no usable coordinates','A malformed active destination reaches the provider.'],
  ['updated','Finding the updated route…','A route result is superseded by a newer request or data generation.'],
  ['unknown','Routing is unavailable','An unrecognized backend status is mapped to the generic message.'],
];
for (const [id,text,when] of driveStates) add('onroad-'+id,'onroad','Driving: '+id.replaceAll('-',' '),
  'Effective offline routing is on, a destination is set, and navInstruction is invalid or last arrived more than 2.5 seconds ago. '+when,
  'The bottom bar replaces arrival/time-left/street with this reason and keeps End route. The turn card is hidden when its own instruction state is missing/invalid or outside the 0–2.5 second freshness window. The green engagement styling here is sample state, not part of this change.',
  replace(driveBase,'Waiting for a fresh GPS fix',esc(text)));
let normal=read('onroadnav').replace('[Street]','Market St').replace('[ETA]','5:18 PM').replace('[min]','12 min').replace('[mi]','8.4 mi').replace('[Current street name]','Market Street');
add('onroad-fresh','onroad','Driving: fresh guidance (reference)','An active local route has fresh, valid GPS/instructions.','Reference: normal turn card, arrival/time-left and street use the existing design. This shows what returns after a waiting/error state clears.',normal,{reference:true});
add('onroad-stale-card','onroad','Driving: turn card expires separately',
  'Offline routing is on and the card\'s NavInstructionState timestamp is missing, malformed, in the future or older than 2.5 seconds. In this example navInstruction on the message bus is still fresh.',
  'Only the turn card is hidden by its new freshness check. The bottom bar checks a separate message timestamp, so its arrival/time-left can remain until that message also expires.',
  normal.replace(/    <div style="position: absolute; left: 18px; top: 128px;[\s\S]*?(?=    <div style="position: absolute; left: 50%;)/,''));

// New data-management screen, including every distinct operation/guard state.
function dataScreen({on=true,runtime=true,packages=[['Iowa','Active',280]],busy=false,locked=false,note='Park and end the route to change routing data'}) {
  const disabled=busy||locked;
  const rows=row('Use offline routes','Saved places and rerouting without a connection',toggle(on,disabled),disabled)+
    row('Routing software',runtime?'Ready for offline routes':'Set up before installing routing data',button('Set up',disabled),disabled)+
    row('Install routing data','Open a routing package link while parked',button('Install from link',disabled),disabled)+
    packages.map(([title,state,size])=>row(title,`${state} · ${size} MiB · OpenStreetMap contributors`,`<div style="display:flex;gap:10px">${button('Use',disabled)}${button('Remove',disabled,true)}</div>`,disabled)).join('');
  return page('Offline routes',`<div class="page"><style>.row{height:66px}.disabled .label{color:#797C80}.disabled .sub{color:#5A6067}</style><div style="flex:1;padding:18px 20px 14px;min-height:0;display:flex"><div class="panel" style="flex:1"><div class="panelhead"><h2>Offline routes</h2><span class="sub">Routing data is separate from speed-limit maps. Place search stays online.</span></div>${rows}</div></div>${footer(note,busy?'<button class="back" style="width:auto;padding:0 26px;font-size:18px;font-weight:600">Cancel</button>':'')}</div>`);
}
const management=[
  ['setup','First setup','Open Offline routes before installing the runtime or any bundle.',{on:false,runtime:false,packages:[]}],
  ['empty','Software ready, no package','The runtime is installed, but no routing package is installed yet.',{on:false,packages:[]}],
  ['installed','Installed, not selected','A valid package is installed but no package is selected (for example after a CLI install).',{on:false,packages:[['Iowa','Installed',280]]}],
  ['ready','Active package, feature on','Iowa is selected and the persistent Use offline routes switch is on.',{}],
  ['off','Active package, feature off','Iowa remains selected, but the persistent offline-routing switch is off.',{on:false}],
  ['preparing','Preparing software','Set up is running, or installation has not yet reported a byte total.',{on:false,runtime:false,packages:[],busy:true,note:'Preparing offline routes…'}],
  ['downloading','Downloading package','The link installer has a byte total; this example is 42% complete.',{packages:[],busy:true,note:'Installing routing data · 42%'}],
  ['locked','Controls locked','The car is onroad, or a destination is still set even though the car is offroad.',{locked:true}],
  ['done','Operation complete','Setup, package activation, installation, or removal completed successfully.',{note:'Done'}],
  ['cancelled','Installation cancelled','The user pressed Cancel and the worker has finished cancelling.',{packages:[],note:'Installation cancelled'}],
  ['failed','Installation failed','A setup/download operation raised an unclassified exception (such as a failed connection).',{packages:[],note:'Installation failed. Check the connection and package.'}],
  ['no-space','Not enough storage','The installer cannot retain its storage reserve while staging the package.',{packages:[],note:'There is not enough storage for this package'}],
  ['incompatible','Package verification failed','The manifest/runtime version, file size, or SHA-256 validation fails.',{note:'Routing data needs to be installed again'}],
  ['exists','Conflicting package ID','A different package uses an immutable ID that is already installed.',{note:'This package is already installed with different data'}],
  ['busy','Package still in use','Removal cannot obtain the native reader lease.',{note:'Routing is busy. Trying again…'}],
  ['guard','Parked state changed','The car starts a drive or acquires a destination during a mutation.',{locked:true,note:'Park and end the route to change routing data'}],
  ['bad-link','Non-HTTPS link rejected','A link with at least 8 characters passes the keyboard length gate but fails the installer HTTPS check.',{note:'This place has no usable coordinates'}],
  ['setup-timeout','Setup timed out','The software installer reaches its setup subprocess deadline.',{note:'The route took too long. Trying again…'}],
];
for (const [id,title,when,options] of management) add('data-'+id,'data',title,when,
  'New management page. Mutating rows are disabled while an operation is busy or the parked/no-destination guard fails. Cancel appears only while busy. Use/Remove are compact row actions; no new removal-confirmation dialog was added.',dataScreen(options),
  ['busy','bad-link','setup-timeout'].includes(id)?{finding:id==='busy'?'The message promises a retry, but the management action does not automatically retry.':id==='bad-link'?'Shared route-error wording is inappropriate for a package URL. This is shown faithfully for review; a copy fix is pending approval.':'Shared route-timeout wording is inappropriate for software setup. This is shown faithfully for review; a copy fix is pending approval.'}:{});

function linkKeyboard(typed) {
  return page('Routing package link',`<div class="page"><div style="height:146px;flex-shrink:0;padding:14px 16px 10px;display:flex;flex-direction:column;gap:10px"><div style="display:flex;align-items:center;gap:12px;height:56px"><div class="words" style="padding:0 4px"><strong style="font-size:24px;font-weight:800">Routing package link</strong><span style="font-size:15px;color:#AEB6C2">Use an HTTPS link to a routing package manifest</span></div><button class="btn" style="height:56px;padding:0 24px;font-size:17px;font-weight:700">Cancel</button></div><div class="kfield">${esc(typed)}</div></div>${keyPanel('Install',typed.length>=8)}</div>`);
}
add('link-empty','link','Package link: empty','Tap Install from link on the management page while mutations are allowed.','Uses the existing Essentials keyboard with a new title, explanatory line, and Install action. Install is disabled until at least 8 characters are entered.',linkKeyboard(''));
add('link-entered','link','Package link: entered','The package-link field has at least 8 characters. This example is an illustrative HTTPS address, not a published Iowa download URL.','Install becomes enabled by length; HTTPS/manifest validity is checked after submission. The URL is ordinary unmasked text.',linkKeyboard('https://maps.example.org/iowa/manifest.json'));
add('mapbox-help','mapbox','Optional Mapbox help','Open How to add / How to change from Navigation while effective offline routing is on.','Only the subtitle changes to Optional: online search and speed-limit filling. The existing four steps and their online-route wording remain.',read('mapboxkeylocal'));

const groups=[['onroad','Driving screen'],['settings','Navigation settings and search'],['places','Saved places and old recents'],['preview','Route preview'],['data','Routing data management'],['link','Package link keyboard'],['mapbox','Mapbox help']];
const findings=[
 'These are retrospective approval drafts. The earlier implementation did not receive owner approval of its UI. No screen in this set is marked approved.',
 'Normal driving status is unchanged visually when instructions are fresh. Waiting/error text appears only with offline routing on and an active destination; it replaces arrival/time-left/street. Turn-card freshness is checked separately.',
 'New settings entry/search wording appears even while offline routing is off. The local badge, preview notes, optional Mapbox subtitle and driving status require effective offline routing on.',
 'Legacy name-only recents currently lose their attempted query when opening search; the public-key notice can mask the new no-coordinates message. Both the visible fallback and stored error text are included.',
 'Package URL and software-timeout errors currently reuse inappropriate route wording. A busy removal says Trying again but does not schedule an automatic management retry. These are review findings, not fixes applied in this design-only pass.',
 'The separate existing Display › Map screen still has its older routing-without-a-connection description. Only Navigation and the search index were corrected in the implementation.',
 'The implementation updated 12 translation catalogs and added 11 fallback-font characters. The approval drafts here show English; there was no intended redesign of existing translated screens.',
];
const manifest={title:'Valhalla UI approval review',status:'pending owner approval',scope:'Only the Valhalla feature diff against HEAD on branch valhalla.',effectiveOn:'Persistent Use offline routes is on or TANDEM_ROUTING=1, unless TANDEM_ROUTING=0 or any of TANDEM_SETTINGS/HOME/ONROAD/SIDEBAR=0 overrides it.',groups:groups.map(([id,title])=>({id,title,count:states.filter(s=>s.group===id).length})),findings,states};
fs.writeFileSync(path.join(__dirname,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
const galleryCSS=`body{margin:0;background:#090C10;color:#F2F5F9;font:16px/1.5 system-ui,sans-serif}main{max-width:1240px;margin:auto;padding:28px 24px 64px}h1{font-size:34px;margin:0 0 10px}h2{font-size:25px;margin:36px 0 12px}h3{margin:0;font-size:20px}p{margin:8px 0 14px}.muted{color:#AEB6C2}.tag{display:inline-block;background:#3A2026;color:#F4AFB7;padding:5px 10px;border-radius:8px;font-weight:650;font-size:13px}nav{position:sticky;top:0;z-index:2;background:#090C10ed;padding:12px 0;display:flex;flex-wrap:wrap;gap:8px}nav button{font:inherit;background:#1E2227;border:1px solid #343B45;color:#F2F5F9;padding:8px 12px;border-radius:10px;cursor:pointer}nav button.active{background:#5AAAF8;color:#0B1A2B;border-color:#5AAAF8}article{background:#16191D;border:1px solid #252A31;border-radius:18px;margin-bottom:24px;padding:20px}article img{display:block;width:100%;height:auto;border-radius:10px;background:#000}a{color:#8CC4FA}details{background:#16191D;padding:16px;border-radius:14px}li{margin:8px 0}.finding{border-left:3px solid #F0B35A;padding:10px 14px;background:#2B2418;color:#F3D6A6}.links{display:flex;gap:16px;font-size:14px}.count{font-size:14px;color:#AEB6C2}label{font-weight:700}.hidden{display:none}dialog{padding:14px;border:1px solid #343B45;border-radius:16px;background:#090C10;max-width:96vw;max-height:96vh;color:#F2F5F9}dialog::backdrop{background:#000d}dialog img{max-width:92vw;max-height:82vh}dialog button{float:right;font:inherit;padding:6px 14px;margin-bottom:10px}`;
const groupsHTML=groups.map(([id,title])=>`<section data-group="${id}"><h2>${title} <span class="count">${states.filter(s=>s.group===id).length} states</span></h2>${states.filter(s=>s.group===id).map(s=>`<article id="${s.id}"><span class="tag">${s.reference?'Existing design reference':'Approval pending'}</span><h3>${esc(s.title)}</h3><p><label>When it appears:</label> ${esc(s.when)}</p><p class="muted"><label>What changed:</label> ${esc(s.change)}</p>${s.finding?`<p class="finding">${esc(s.finding)}</p>`:''}<a href="../screenshots/${s.file}.png" class="zoom"><img src="../screenshots/${s.file}.png" loading="lazy" width="1125" height="563" alt="${esc(s.title)}"></a><p class="links"><a href="../${s.file}.html">Open HTML mock</a><a href="../screenshots/${s.file}.png">Full-size PNG</a><a href="#top">Back to top</a></p></article>`).join('')}</section>`).join('');
const gallery=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Valhalla UI approval review</title><style>${galleryCSS}</style></head><body><main id="top"><span class="tag">${states.length} drafts · owner approval pending</span><h1>Valhalla UI changes</h1><p>All visible changes from the feature, with the conditions for each state. These are HTML design mocks, not live-device screenshots. Placeholder roads, places and times are illustrative.</p><p class="muted"><label>Offline routing is on when:</label> ${esc(manifest.effectiveOn)}</p><details><summary>Scope, behavior and implementation gaps found during this review</summary><ul>${findings.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details><nav><button class="active" data-filter="all">All ${states.length}</button>${groups.map(([id,title])=>`<button data-filter="${id}">${title}</button>`).join('')}</nav>${groupsHTML}<dialog id="zoom"><button onclick="this.parentElement.close()">Close</button><img alt="Full-size mock"></dialog><script>document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('[data-group]').forEach(s=>s.classList.toggle('hidden',b.dataset.filter!=='all'&&b.dataset.filter!==s.dataset.group));});document.querySelectorAll('.zoom').forEach(a=>a.onclick=e=>{e.preventDefault();const d=document.getElementById('zoom');d.querySelector('img').src=a.href;d.showModal();});</script></main></body></html>`;
fs.writeFileSync(path.join(__dirname,'index.html'),gallery);

// Compact review boards for showing all families directly in the chat. Full states stay in the gallery.
const boards={
  onroad:['onroad-fresh','onroad-stale-card','onroad-gps','onroad-rerouting'],
  settings:['nav-entry','nav-online','nav-local','search-valhalla'],
  places:['places-ready','places-not-ready','recent-no-coordinates','recent-coordinate-error'],
  preview:['preview-ready','preview-alternative','preview-pending','preview-coverage'],
  data:['data-setup','data-ready','data-downloading','data-locked'],
  operations:['data-done','data-cancelled','data-no-space','data-bad-link'],
  link:['link-empty','link-entered'],
  mapbox:['mapbox-help'],
};
for (const [id,ids] of Object.entries(boards)) {
  const title={operations:'Management completion and errors',...Object.fromEntries(groups)}[id];
  const board=`<!doctype html><html><head><meta charset="utf-8"><style>${fonts.replaceAll("../../../assets/","../../../../assets/")}body{margin:0;background:#090C10;color:#F2F5F9;font-family:Figtree,sans-serif}main{width:1500px;padding:24px;box-sizing:border-box}h1{margin:0 0 4px;font-size:30px}.status{color:#F4AFB7;margin:0 0 20px;font-size:16px}.grid{display:grid;grid-template-columns:${ids.length===1?'1fr':'1fr 1fr'};gap:18px}article{background:#16191D;border-radius:16px;padding:14px;min-width:0}h2{margin:0 0 8px;font-size:21px}img{width:100%;display:block;border-radius:8px}p{font-size:16px;line-height:1.4;color:#C9D0DA;margin:10px 0 0}</style></head><body><main><h1>${esc(title)}</h1><div class="status">Approval drafts · full-size mocks and every status variant are in the review gallery</div><div class="grid">${ids.map(key=>{const s=states.find(s=>s.id===key);return `<article><h2>${esc(s.title)}</h2><img src="../screenshots/${s.file}.png"><p>${esc(s.when)}</p></article>`;}).join('')}</div></main></body></html>`;
  fs.writeFileSync(path.join(__dirname,'board-'+id+'.html'),board);
}
fs.writeFileSync(path.join(__dirname,'names.json'),JSON.stringify(states.map(s=>s.file),null,2)+'\n');
console.log(`${states.length} approval mocks; gallery: ${path.join(__dirname,'index.html')}`);
// Keep the historical review clearly labelled when the owner revises the direction.
if (fs.existsSync(path.join(__dirname,'revision-2/index.html'))) {
  const target=path.join(__dirname,'index.html');
  fs.writeFileSync(target,fs.readFileSync(target,'utf8').replace('<main id="top">',
    '<main id="top"><p style="padding:18px;border:2px solid #5AAAF8;border-radius:14px;background:#1F2E45"><strong>Superseded by owner feedback.</strong> <a href="revision-2/index.html">Open revision 2: routing preferences, integrated regions, and status chips.</a> The URL-entry flow is rejected. This page is a historical implementation audit.</p>'));
}
