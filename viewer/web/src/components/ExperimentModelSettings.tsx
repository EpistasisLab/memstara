import {createContext, useEffect, useRef, useState} from 'react';
import {Check, ChevronDown, Eye, EyeOff, LoaderCircle, Cpu} from 'lucide-react';
import {stageModelRows} from '../lib/stageModels';
import './experiment-model-settings.css';

export const ExperimentModelContext = createContext<string | undefined>(undefined);
export type ModelConnection = {id: string; provider: string; model: string; api_base: string; region: string; checked_at: string; settings?: Partial<GenerationSettings>};
const providers = {openai: 'OpenAI', anthropic: 'Anthropic', azure_foundry: 'Azure Foundry', openrouter: 'OpenRouter', local: 'Local / self-hosted', bedrock: 'Amazon Bedrock'};
type Provider = keyof typeof providers;
type Capabilities = {supports_temperature: boolean | null; supports_effort: boolean | null; effort_levels: string[] | null; default_effort: string | null; default_temperature?: number | null; temperature_effort_levels?: string[] | null};
type ModelOption = {id?: string; model: string; label: string; capabilities: Capabilities};
type ModelCatalog = {source: string; version: string; providers: {id: Provider; label: string; custom_model_name: boolean; can_list_models: boolean; models: ModelOption[]}[]; controls: {temperature: {default: number | null; minimum: number; maximum: number}; max_tokens: {default: number; exclusiveMinimum: number; maximum: number}}};
type ConfiguredProfile = {role: string; roles: string[]; provider: Provider; model: string; api_base: string; region: string; auth_type: string; settings: Partial<GenerationSettings>; capabilities: Capabilities; credentials_available: boolean};
const roleLabels: Record<string, string> = {question: 'Question generation', hypothesis: 'Hypothesis', data: 'Data', ml: 'ML', interpretation: 'Interpretation', explanation: 'Explanation'};
const profileRoles = (profile: ConfiguredProfile) => profile.roles.length === 6 ? 'All agents' : profile.roles.map(role => roleLabels[role] || role).join(', ');
type GenerationSettings = {temperature?: number; effort?: string; max_tokens: number};
const emptyForm = {provider: 'azure_foundry' as Provider, model: '', api_key: '', api_base: '', region: '', auth_type: 'api_key', access_key_id: '', secret_access_key: '', session_token: ''};

export default function ExperimentModelSettings({onChange, onValidityChange}: {
  onChange: (connection: ModelConnection | null) => void; onValidityChange: (error: string) => void;
}) {
  const [mode, setMode] = useState<'current' | 'custom'>('current');
  const [current, setCurrent] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [configured, setConfigured] = useState<ConfiguredProfile[]>([]);
  const [currentAllowed, setCurrentAllowed] = useState<boolean | undefined>();
  const [setupRequired, setSetupRequired] = useState(false);
  const [currentConnection, setCurrentConnection] = useState<ModelConnection | null>(null);
  const [defaultsPending, setDefaultsPending] = useState(true);
  const [currentError, setCurrentError] = useState('');
  const selectionTouched = useRef(false);
  const checkedHere = useRef(false);
  const providerNotice = currentError || (setupRequired ? 'Set up an Azure Foundry model to continue. Server model defaults are not ready.' : 'Only Azure Foundry is available. Set up an Azure Foundry model to continue.');
  useEffect(() => {
    if (mode === 'current') onValidityChange(defaultsPending ? 'Loading current model…' : currentAllowed === false ? providerNotice : '');
  }, [mode, defaultsPending, currentAllowed, providerNotice, onValidityChange]);
  const [defaultRole, setDefaultRole] = useState('');
  const [useServerKey, setUseServerKey] = useState(false);
  const formTouched = useRef(false);
  const [form, setForm] = useState(emptyForm);
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [catalogError, setCatalogError] = useState('');
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [selection, setSelection] = useState('');
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [settings, setSettings] = useState<GenerationSettings>({max_tokens: 4096});
  const [listed, setListed] = useState<ModelOption[]>([]);
  const [listing, setListing] = useState(false);
  const [listMessage, setListMessage] = useState('');
  const listingRequest = useRef<AbortController | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void fetch('/control/health', {signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)])})
      .then(async response => {
        if (!response.ok) throw Error();
        const body = await response.json();
        const rows = stageModelRows({...body.llm, stage_models: body.stage_models});
        if (!controller.signal.aborted) setCurrent([...new Set(rows.filter(r => r.provider === 'azure_foundry' && r.model !== 'Not recorded').map(r => `${providers[r.provider as Provider] || r.provider} · ${r.model}`))]);
      }).catch(() => {}).finally(() => {if (!controller.signal.aborted) setLoaded(true);});
    return () => {controller.abort(); request.current?.abort(); listingRequest.current?.abort();};
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetch('/control/model-defaults', {signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)])})
      .then(async response => {if (!response.ok) throw Error(); return response.json();})
      .then(body => {
        if (controller.signal.aborted || checkedHere.current) return;
        const connection: ModelConnection | null = body.connection ?? null;
        if (connection && (!/^[a-f0-9]{32}$/.test(connection.id) || connection.provider !== 'azure_foundry' || !connection.model)) throw Error();
        if (Array.isArray(body.profiles)) {
          setConfigured(body.profiles.filter((profile: ConfiguredProfile) => profile.provider === 'azure_foundry'));
          setCurrentAllowed(body.current_allowed ?? (body.profiles.length > 0 && body.profiles.every((profile: ConfiguredProfile) => profile.provider === 'azure_foundry')));
          setSetupRequired(body.setup_required === true);
        }
        setCurrentConnection(connection); setCurrentError(body.current_error || '');
        if (!selectionTouched.current && !formTouched.current) {
          onChange(connection);
          if (body.setup_required) {
            setMode('custom'); onValidityChange('Enter your model connection and select Check & use model.');
          }
        }
      })
      .catch(() => {
        if (controller.signal.aborted || checkedHere.current) return;
        setCurrentAllowed(false); setSetupRequired(true);
        setCurrentError('Current model could not be loaded. Reopen Add experiment to retry, or set up a model.');
        if (!selectionTouched.current && !formTouched.current) {
          setMode('custom'); onValidityChange('Set up and check a model to continue.');
        }
      }).finally(() => {if (!controller.signal.aborted) setDefaultsPending(false);});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogError('');
    void fetch('/control/model-catalog', {signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)])})
      .then(async response => {if (!response.ok) throw Error(); const body = await response.json();
        if (!body.providers?.length || !body.controls) throw Error();
        if (!controller.signal.aborted) setCatalog({...body, providers: body.providers.filter((row: ModelCatalog['providers'][number]) => row.id === 'azure_foundry')});})
      .catch(() => {if (!controller.signal.aborted) setCatalogError('Model options could not be loaded.');});
    return () => controller.abort();
  }, [catalogAttempt]);
  const providerInfo = catalog?.providers.find(row => row.id === form.provider);
  const selected = providerInfo?.models.find(row => row.id === selection);
  function defaults(nextCaps: Capabilities) {
    return {max_tokens: catalog!.controls.max_tokens.default,
      ...(nextCaps.supports_temperature ? {temperature: nextCaps.default_temperature ?? catalog!.controls.temperature.default ?? undefined} : {}),
      ...(nextCaps.supports_effort ? {effort: nextCaps.default_effort ?? undefined} : {})};
  }
  useEffect(() => {
    if (!catalog || caps || selected || selection.startsWith('provider:') || !form.model.trim()) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void fetch(`/control/model-capabilities?provider=${encodeURIComponent(form.provider)}&model=${encodeURIComponent(form.model.trim())}`,
        {signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)])})
        .then(async response => {if (!response.ok) throw Error(); return response.json();})
        .then(body => {if (!controller.signal.aborted) {setCaps(body.capabilities); setSettings(defaults(body.capabilities));}})
        .catch(() => {if (!controller.signal.aborted) setError('Could not load model settings. Select a Motoro model or enter the model ID again.');});
    }, 250);
    return () => {clearTimeout(timer); controller.abort();};
  }, [catalog, form.provider, form.model, selection, caps]);
  function applyConfiguredProfile(profile: ConfiguredProfile) {
    if (profile.provider !== 'azure_foundry') return;
    invalidate(); stopListing(); setListed([]); setShowKey(false);
    formTouched.current = true;
    setDefaultRole(profile.role); setUseServerKey(profile.credentials_available);
    setForm({...emptyForm, provider: profile.provider, model: profile.model, api_base: profile.api_base,
      region: profile.region, auth_type: profile.auth_type || 'api_key'});
    const match = catalog?.providers.find(row => row.id === profile.provider)?.models.find(row => row.model === profile.model);
    setSelection(match?.id || 'manual'); setCaps(profile.capabilities);
    setSettings({...defaults(profile.capabilities),
      ...(profile.settings.max_tokens !== undefined ? {max_tokens: profile.settings.max_tokens} : {}),
      ...(profile.capabilities.supports_temperature && profile.settings.temperature !== undefined ? {temperature: profile.settings.temperature} : {}),
      ...(profile.capabilities.supports_effort && profile.settings.effort !== undefined ? {effort: profile.settings.effort} : {})});
  }
  useEffect(() => {
    if (mode === 'custom' && !formTouched.current && catalog && configured.length) applyConfiguredProfile(configured[0]);
  }, [mode, catalog, configured]);

  function selectModel(value: string) {
    invalidate(); setSelection(value);
    const option = providerInfo?.models.find(row => row.id === value) || listed.find(row => `provider:${row.model}` === value);
    setCaps(option?.capabilities || null);
    if (option) setSettings(defaults(option.capabilities));
    setForm(previous => ({...previous, model: providerInfo?.custom_model_name && !value.startsWith('provider:') ? previous.model : option?.model || ''}));
  }
  function stopListing() {
    listingRequest.current?.abort(); listingRequest.current = null; setListing(false); setListMessage('');
  }
  function payload() {
    return {provider: form.provider, model: form.model.trim(),
      ...(reuseCredentials ? {default_role: defaultRole} : !awsCredentials ? {api_key: form.api_key} : {}),
      ...(hasEndpoint ? {api_base: form.api_base.trim()} : {}),
      ...(form.provider === 'bedrock' ? {region: form.region.trim(), auth_type: form.auth_type,
        ...(awsCredentials && !reuseCredentials ? {access_key_id: form.access_key_id, secret_access_key: form.secret_access_key, session_token: form.session_token} : {})} : {})};
  }
  async function loadModels() {
    stopListing(); const controller = new AbortController(); listingRequest.current = controller; setListing(true);
    try {
      const response = await fetch('/control/model-connections/models', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload()), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)])});
      const body = await response.json();
      if (!response.ok) throw Error(body.error || 'Model list unavailable.');
      if (listingRequest.current !== controller) return;
      setListed(body.models);
      setListMessage(`${body.models.length} models loaded${body.truncated ? ' (partial list)' : ''}. Choose one in the Model menu. Check & use model confirms compatibility.`);
    } catch (reason) {
      if (listingRequest.current === controller && !controller.signal.aborted) setListMessage(reason instanceof Error ? reason.message : 'Model list unavailable.');
    } finally {if (listingRequest.current === controller) {setListing(false); listingRequest.current = null;}}
  }

  function invalidate() {
    formTouched.current = true;
    request.current?.abort(); request.current = null;
    setBusy(false); setError(''); onChange(null);
    onValidityChange('Check your model connection to continue.');
  }
  function choose(next: 'current' | 'custom') {
    selectionTouched.current = true;
    invalidate(); stopListing(); setListed([]); setSelection(''); setCaps(null); setMode(next); setShowKey(false); setForm(emptyForm); setDefaultRole(''); setUseServerKey(false); formTouched.current = false;
    if (next === 'current') onChange(currentConnection);
    onValidityChange(next === 'current' ? defaultsPending ? 'Loading current model…' : currentAllowed === false ? providerNotice : '' : 'Enter your model connection and select Check & use model.');
  }
  function field(key: keyof typeof emptyForm, value: string) {
    invalidate(); stopListing(); if (['api_base', 'region', 'auth_type'].includes(key)) setUseServerKey(false); if (key === 'model' && !selected) setCaps(null); setForm(previous => ({...previous, [key]: value}));
  }
  const configuredProfile = configured.find(profile => profile.role === defaultRole);
  const canReuseCredentials = !!configuredProfile?.credentials_available && form.provider === configuredProfile.provider && form.api_base.trim() === configuredProfile.api_base && form.region.trim() === configuredProfile.region && (form.provider !== 'bedrock' || form.auth_type === configuredProfile.auth_type);
  const reuseCredentials = useServerKey && canReuseCredentials;
  const awsCredentials = form.provider === 'bedrock' && form.auth_type === 'aws_credentials';
  const hasEndpoint = form.provider === 'azure_foundry' || form.provider === 'local';
  const valid = form.provider === 'azure_foundry' && !!catalog && !!caps && Number.isInteger(settings.max_tokens) && settings.max_tokens > 0 && settings.max_tokens <= catalog.controls.max_tokens.maximum && (settings.temperature === undefined || Number.isFinite(settings.temperature) && settings.temperature >= catalog.controls.temperature.minimum && settings.temperature <= catalog.controls.temperature.maximum) && !!form.model.trim() && (!hasEndpoint || !!form.api_base.trim()) &&
    (reuseCredentials || !!form.api_key.trim());

  async function check() {
    if (!valid || busy) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError('');
    onValidityChange('Checking your model connection…');
    const connectionPayload = {...payload(), settings, ...(selected ? {catalog_id: selected.id} : {})};
    try {
      const response = await fetch('/control/model-connections/check', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(connectionPayload), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(55000)])});
      const body = await response.json();
      if (!response.ok) throw Error(body.error || 'Connection could not be checked. Try again.');
      const connection: ModelConnection = body.connection;
      if (!connection?.id || connection.provider !== form.provider || connection.model !== form.model.trim()) throw Error('Unexpected connection response. Try again.');
      if (request.current !== controller) return;
      selectionTouched.current = true;
      checkedHere.current = true; setDefaultsPending(false);
      setCurrentConnection(connection); setCurrentAllowed(true); setSetupRequired(false);
      setCurrentError(''); setMode('current'); setShowKey(false);
      setForm(previous => ({...previous, api_key: '', secret_access_key: '', access_key_id: '', session_token: ''}));
      onChange(connection); onValidityChange('');
    } catch (reason) {
      if (request.current !== controller || controller.signal.aborted) return;
      const message = reason instanceof Error && reason.name !== 'TimeoutError' ? reason.message : 'Connection timed out. Please try again.';
      setError(message); onValidityChange('Check your model connection to continue.');
    } finally {if (request.current === controller) {setBusy(false); request.current = null;}}
  }

  return <section className="experiment-model-settings" aria-labelledby="experiment-model-heading">
    <header className="experiment-model-heading"><span className="experiment-model-icon"><Cpu size={21} aria-hidden="true"/></span>
      <div><h4 id="experiment-model-heading">AI model</h4><p>Use an Azure Foundry model for your agents.</p></div>
    </header>
    {setupRequired && mode === 'custom' && <p className="experiment-model-notice" role="status">{currentError || 'No server model is ready. Enter your Azure connection below; you do not need to edit .env or restart the app.'}</p>}
    <fieldset className="experiment-model-modes"><legend className="sr-only">Model connection</legend>
      <label className={mode === 'current' ? 'is-selected' : ''}><input type="radio" name="experiment-model-mode" disabled={defaultsPending || currentAllowed === false} checked={mode === 'current'} onChange={() => choose('current')}/><span><strong>Use current model</strong><small>{currentConnection ? 'Use your saved model for all agents.' : 'Use the defaults configured for each agent.'}</small></span>{mode === 'current' && <Check size={17} aria-hidden="true"/>}</label>
      <label className={mode === 'custom' ? 'is-selected' : ''}><input type="radio" name="experiment-model-mode" checked={mode === 'custom'} onChange={() => choose('custom')}/><span><strong>Set up a model</strong><small>Start from your defaults or use another model.</small></span>{mode === 'custom' && <Check size={17} aria-hidden="true"/>}</label>
    </fieldset>
    {mode === 'current' && currentAllowed === false && <p className="experiment-model-notice" role="alert">{providerNotice}</p>}
    {mode === 'current' ? <div className="experiment-model-current" role="status">
      {defaultsPending ? <p>Loading current model…</p> : currentConnection ? <>
        <div className="experiment-model-ready"><Check size={20} aria-hidden="true"/><div><strong>Model ready</strong><p>{providers[currentConnection.provider as Provider]} · {currentConnection.model}</p><small>All agents · Automatically selected for new experiments.</small></div><button type="button" onClick={() => choose('custom')}>Change</button></div>
        <details><summary>Connection & settings</summary><dl>
          <div><dt>Endpoint</dt><dd className="break-words">{currentConnection.api_base}</dd></div>
          <div><dt>Credentials</dt><dd>Saved on the server</dd></div>
          <div><dt>Temperature</dt><dd>{currentConnection.settings?.temperature ?? 'Automatic'}</dd></div>
          <div><dt>Reasoning effort</dt><dd>{currentConnection.settings?.effort ?? 'Automatic'}</dd></div>
          <div><dt>Maximum output tokens</dt><dd>{currentConnection.settings?.max_tokens ?? 'Automatic'}</dd></div>
        </dl></details>
      </> : configured.length ? <>
        <p className="experiment-default-source">Loaded from this server’s .env configuration.</p>
        {configured.map(profile => <article className="experiment-default-card" key={profile.role}>
          <strong>{providers[profile.provider]} · {profile.model}</strong><p>{profileRoles(profile)}</p>
          <details><summary>Connection & settings</summary><dl>
            {profile.api_base && <div><dt>Endpoint</dt><dd>{profile.api_base}</dd></div>}
            {profile.region && <div><dt>AWS Region</dt><dd>{profile.region}</dd></div>}
            <div><dt>Credentials</dt><dd>{profile.credentials_available ? 'Configured on the server' : profile.provider === 'local' ? 'No API key configured (optional)' : 'Not configured'}</dd></div>
            <div><dt>Temperature</dt><dd>{profile.settings.temperature ?? 'Automatic'}</dd></div>
            <div><dt>Reasoning effort</dt><dd>{profile.settings.effort ?? 'Automatic'}</dd></div>
            <div><dt>Maximum output tokens</dt><dd>{profile.settings.max_tokens ?? catalog?.controls.max_tokens.default ?? 'Automatic'}</dd></div>
          </dl></details>
        </article>)}
      </> : current.length ? current.map(label => <p key={label}>{label}</p>) : <p>{loaded ? 'Current model details are unavailable.' : 'Loading current model…'}</p>}
    </div> : <div className="experiment-model-form">
      {configured.length > 0 && <div className="experiment-default-prefill">
        {configured.length > 1 && <label htmlFor="experiment-default-profile">Start from a configured model<select id="experiment-default-profile" value={defaultRole} disabled={!catalog} onChange={e => {const profile = configured.find(row => row.role === e.target.value); if (profile) applyConfiguredProfile(profile);}}><option value="" disabled>Choose a configured model</option>{configured.map(profile => <option key={profile.role} value={profile.role}>{profileRoles(profile)} · {profile.model}</option>)}</select><small>Example: choose the Explanation model to copy its connection settings.</small></label>}
        <p>{defaultRole ? 'Filled from your configured model. Changes apply to all agents in this experiment only.' : 'Choose an Azure Foundry deployment for this experiment.'}</p>
      </div>}
      <div className="experiment-model-grid">
        <label htmlFor="experiment-model-provider">Provider<select id="experiment-model-provider" value="azure_foundry" disabled><option value="azure_foundry">Azure Foundry</option></select><small>Azure Foundry is fixed for this application.</small></label>
        <label htmlFor="experiment-model-choice">{providerInfo?.custom_model_name ? 'Base model' : 'Model'}<div className="experiment-model-select"><select id="experiment-model-choice" aria-describedby="experiment-base-model-help" value={selection} onChange={e => selectModel(e.target.value)}>
          <option value="">Choose a model</option><optgroup label="Motoro catalog">{providerInfo?.models.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</optgroup>
          {listed.length > 0 && <optgroup label="From your provider">{listed.map(row => <option key={row.model} value={`provider:${row.model}`}>{row.label}</option>)}</optgroup>}
          <option value="manual">Not listed — enter deployment name</option></select><ChevronDown size={16} aria-hidden="true"/></div><small id="experiment-base-model-help">Select the model behind your Azure deployment. This determines which settings are available.<span className="experiment-field-example">Example: <code>GPT-4.1</code>. This catalog is not your Azure deployment list.</span></small></label>
      </div>
      {(providerInfo?.custom_model_name || selection === 'manual') && <label htmlFor="experiment-model-id">{form.provider === 'azure_foundry' ? 'Azure deployment name' : 'Model ID'}<input id="experiment-model-id" aria-describedby="experiment-deployment-help" value={form.model} autoComplete="off" spellCheck={false} placeholder={form.provider === 'azure_foundry' ? 'Your Azure deployment name' : 'Exact model ID from your provider'} onChange={e => field('model', e.target.value)}/><small id="experiment-deployment-help">Copy the exact deployment name from Azure Foundry. This is the name used for requests.<span className="experiment-field-example">Example: <code>research-model</code> could be your deployment of GPT-4.1. Use your own deployment name; it may differ from the base model.</span></small></label>}
      {!catalog && <p className="experiment-model-notice" role="status">{catalogError || 'Loading model options from Motoro…'}{catalogError && <button type="button" onClick={() => setCatalogAttempt(value => value + 1)}>Retry</button>}</p>}

      {hasEndpoint && <label htmlFor="experiment-model-endpoint">Endpoint URL<input id="experiment-model-endpoint" aria-describedby="experiment-endpoint-help" type="url" value={form.api_base} placeholder={form.provider === 'azure_foundry' ? 'https://your-resource.services.ai.azure.com' : 'http://host.docker.internal:8000/v1'} onChange={e => field('api_base', e.target.value)}/><small id="experiment-endpoint-help">Paste the endpoint from the Azure resource that hosts your deployment.<span className="experiment-field-example">Example: <code>https://your-resource.services.ai.azure.com</code>. Copy your actual endpoint, including any required path.</span></small></label>}
      {form.provider === 'bedrock' && <div className="experiment-model-grid">
        <label htmlFor="experiment-model-region">AWS Region<input id="experiment-model-region" value={form.region} placeholder="us-east-1" onChange={e => field('region', e.target.value)}/></label>
        <label htmlFor="experiment-model-auth">Authentication<select id="experiment-model-auth" value={form.auth_type} onChange={e => {invalidate(); stopListing(); setUseServerKey(false); setForm(previous => ({...previous, auth_type: e.target.value, api_key: '', access_key_id: '', secret_access_key: '', session_token: ''}));}}><option value="api_key">Bedrock API key</option><option value="aws_credentials">AWS access keys</option></select></label>
      </div>}
      {canReuseCredentials && <label className="experiment-configured-key"><input type="checkbox" checked={useServerKey} onChange={e => {invalidate(); setUseServerKey(e.target.checked); setForm(previous => ({...previous, api_key: '', access_key_id: '', secret_access_key: '', session_token: ''}));}}/><span>Use configured credentials<small>Already stored on the server. No need to enter them again.<span className="experiment-field-example">Example: keep this checked when using the same Azure resource as your server defaults.</span></small></span></label>}
      {!reuseCredentials && (awsCredentials ? <>
        <label htmlFor="experiment-aws-access">Access key ID<input id="experiment-aws-access" autoComplete="off" value={form.access_key_id} onChange={e => field('access_key_id', e.target.value)}/></label>
        <label htmlFor="experiment-aws-secret">Secret access key<input id="experiment-aws-secret" type="password" autoComplete="new-password" value={form.secret_access_key} onChange={e => field('secret_access_key', e.target.value)}/></label>
        <label htmlFor="experiment-aws-session">Session token <span className="experiment-model-optional">Optional</span><input id="experiment-aws-session" type="password" autoComplete="new-password" value={form.session_token} onChange={e => field('session_token', e.target.value)}/></label>
      </> : <label htmlFor="experiment-api-key">{form.provider === 'bedrock' ? 'Bedrock API key' : 'API key'} {form.provider === 'local' && <span className="experiment-model-optional">Optional</span>}
        <div className="experiment-model-secret"><input id="experiment-api-key" type={showKey ? 'text' : 'password'} autoComplete="new-password" spellCheck={false} value={form.api_key} placeholder={form.provider === 'local' ? 'Only if your server requires a key' : 'Paste your API key'} onChange={e => field('api_key', e.target.value)}/><button type="button" aria-label={showKey ? 'Hide API key' : 'Show API key'} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div>
        <small>Your key is stored securely on the server, separately from experiment results.<span className="experiment-field-example">Example source: the API key shown with your Azure resource’s endpoint. Paste the full key, not its name or a masked value.</span></small>
      </label>)}
      {providerInfo?.can_list_models && <div className="experiment-model-listing">
        <button type="button" disabled={listing || (hasEndpoint && !form.api_base.trim()) || (!reuseCredentials && form.provider !== 'local' && !form.api_key.trim())} onClick={() => void loadModels()}>{listing ? 'Loading models…' : 'Load provider models'}</button>
        <p role="status">{listMessage || 'Optional — use your connection to load the provider’s model list.'}</p>
      </div>}
      {caps && catalog && <details className="experiment-model-advanced"><summary>Advanced model settings <span>Optional · settings from Motoro</span></summary>
        <div className="experiment-model-advanced-body">
          <p>These settings apply to every agent in this experiment. Provider limits may be lower than Motoro’s allowed range.</p>
          {configuredProfile?.model === form.model && configuredProfile.provider === form.provider && ((!caps.supports_temperature && configuredProfile.settings.temperature !== undefined) || (!caps.supports_effort && configuredProfile.settings.effort !== undefined)) && <p className="experiment-default-source">Server defaults: {!caps.supports_temperature && configuredProfile.settings.temperature !== undefined ? `temperature ${configuredProfile.settings.temperature}. ` : ''}{!caps.supports_effort && configuredProfile.settings.effort !== undefined ? `reasoning effort ${configuredProfile.settings.effort}. ` : ''}Motoro has not confirmed support for these settings on this model. Choose “Use current model” to keep the server configuration; a new connection uses only confirmed settings.</p>}
          <div className="experiment-model-grid">
            {caps.supports_temperature && <label htmlFor="experiment-temperature">Temperature<input id="experiment-temperature" type="number" min={catalog.controls.temperature.minimum} max={catalog.controls.temperature.maximum} step="0.1" placeholder="Automatic" value={Number.isNaN(settings.temperature) ? '' : settings.temperature ?? ''} onChange={e => {invalidate(); setSettings(previous => ({...previous, temperature: e.target.value === '' ? undefined : Number(e.target.value)}));}}/><small>Leave blank to use Motoro’s default for this model and reasoning mode.<span className="experiment-field-example">Example: <code>0.2</code> requests less variation than a higher temperature; it does not guarantee identical answers.</span></small></label>}
            {caps.supports_effort && <label htmlFor="experiment-effort">Reasoning effort<select id="experiment-effort" value={settings.effort ?? ''} onChange={e => {invalidate(); setSettings(previous => ({...previous, effort: e.target.value || undefined}));}}><option value="">Automatic</option>{(caps.effort_levels ?? (caps.default_effort ? [caps.default_effort] : [])).map(level => <option key={level} value={level}>{level === 'xhigh' ? 'Extra high' : level === 'max' ? 'Maximum' : level[0].toUpperCase() + level.slice(1)}</option>)}</select><small>Higher effort can take longer and cost more.<span className="experiment-field-example">Example: <code>Automatic</code> uses the default for the selected model.</span></small></label>}
            <label htmlFor="experiment-max-tokens">Maximum output tokens<input id="experiment-max-tokens" type="number" min={catalog.controls.max_tokens.exclusiveMinimum + 1} max={catalog.controls.max_tokens.maximum} step="1" value={Number.isNaN(settings.max_tokens) ? '' : settings.max_tokens} onChange={e => {invalidate(); setSettings(previous => ({...previous, max_tokens: e.target.value === '' ? NaN : Number(e.target.value)}));}}/><small>Limits each agent response. A very low limit may cut it short.<span className="experiment-field-example">Example: <code>4096</code> sets a token budget for each response, not for the whole experiment.</span></small></label>
          </div>
          <button type="button" onClick={() => {invalidate(); setSettings(defaults(caps));}}>Reset to Motoro defaults</button>
        </div>
      </details>}
      {error && <p className="experiment-model-error" role="alert">{error}</p>}
      <div className="experiment-model-check"><button className="comb-primary" type="button" disabled={!valid || busy} onClick={() => void check()}>{busy && <LoaderCircle size={16} className="animate-spin" aria-hidden="true"/>}{busy ? 'Checking…' : 'Check & use model'}</button><p>Saves this as your current model for new experiments after a small test request. Your provider may charge for it.</p></div>
    </div>}
  </section>;
}
