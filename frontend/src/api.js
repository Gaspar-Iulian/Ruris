export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function csrfToken() {
  const cookie = document.cookie.split('; ').find((part) => part.startsWith('csrf_access_token='));
  return cookie ? decodeURIComponent(cookie.slice('csrf_access_token='.length)) : '';
}

export async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = {};
  const multipart = body instanceof FormData;
  if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') headers['X-CSRF-TOKEN'] = csrfToken();
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method, headers, credentials: 'same-origin', cache: 'no-store', signal,
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Nu putem contacta aplicația. Verifică conexiunea și încearcă din nou.', 0);
  }
  let data;
  try { data = await response.json(); }
  catch { throw new ApiError('Serverul nu este disponibil momentan. Încearcă din nou.', response.status); }
  if (!response.ok) {
    const message = data.message || (response.status === 401 ? 'Sesiunea a expirat. Autentifică-te din nou.' : 'Cererea nu a putut fi procesată.');
    throw new ApiError(message, response.status);
  }
  return data;
}

export async function apiFile(path, { signal } = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, { credentials: 'same-origin', cache: 'no-store', signal });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Fișierul nu a putut fi descărcat. Verifică conexiunea.', 0);
  }
  if (!response.ok) {
    let message = 'Fișierul nu este disponibil momentan.';
    try { message = (await response.json()).message || message; } catch { /* Keep the download error readable. */ }
    throw new ApiError(message, response.status);
  }
  try { return await response.blob(); }
  catch { throw new ApiError('Descărcarea nu a putut fi încheiată. Încearcă din nou.', 0); }
}
