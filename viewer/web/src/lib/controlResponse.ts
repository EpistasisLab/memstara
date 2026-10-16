/** Proxy outages are uncertain responses, never proof that a start was rejected. */
export async function controlResponse(response: Response) {
  let value;
  try { value = JSON.parse(await response.text()); }
  catch { throw new TypeError(`Server response unavailable (HTTP ${response.status}). Checking connection; saved results are retained.`); }
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new TypeError('Invalid server response. Checking connection; saved results are retained.');
  if ([502, 503, 504].includes(response.status))
    throw new TypeError(`Server temporarily unavailable (HTTP ${response.status}). Saved results are retained.`);
  return value;
}
