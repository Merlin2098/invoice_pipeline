const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }))
    throw Object.assign(new Error(err.message ?? res.statusText), { status: res.status, data: err })
  }
  return res.json()
}

export async function requestUploadUrls(files) {
  return request('POST', '/uploads', {
    files: files.map(f => ({ name: f.name, content_type: f.type || 'application/pdf', size_bytes: f.size })),
  })
}

export async function uploadFileToS3(uploadUrl, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', uploadUrl)
    xhr.setRequestHeader('Content-Type', file.type || 'application/pdf')
    if (onProgress) xhr.upload.onprogress = e => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100))
    xhr.onload = () => xhr.status < 300 ? resolve() : reject(new Error(`S3 PUT failed: ${xhr.status}`))
    xhr.onerror = () => reject(new Error('Network error during S3 upload'))
    xhr.send(file)
  })
}

export async function getInvoiceStatus(invoiceId) {
  return request('GET', `/invoices/${encodeURIComponent(invoiceId)}/status`)
}

export async function listInvoices({ status, limit = 20, nextToken } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (limit) params.set('limit', limit)
  if (nextToken) params.set('next_token', nextToken)
  const qs = params.toString()
  return request('GET', `/invoices${qs ? `?${qs}` : ''}`)
}

export async function sendChat(question) {
  return request('POST', '/chat', { question })
}
