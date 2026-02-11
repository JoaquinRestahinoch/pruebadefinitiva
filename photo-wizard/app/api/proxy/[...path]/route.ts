import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

async function forward(req: NextRequest, params: any) {
  const pathParts = params?.path ?? []
  const path = Array.isArray(pathParts) ? pathParts.join('/') : String(pathParts || '')

  const base = (process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000').replace(/\/+$/,'')
  const url = path ? `${base}/${path}${req.nextUrl.search || ''}` : `${base}${req.nextUrl.search || ''}`

  const headers: Record<string,string> = {}
  for (const [k,v] of req.headers.entries()) {
    if (k.toLowerCase() === 'host') continue
    headers[k] = v
  }

  let body: BodyInit | undefined
  try {
    const arr = await req.arrayBuffer()
    body = arr && arr.byteLength ? Buffer.from(arr) : undefined
  } catch (e) {
    body = undefined
  }

  const resp = await fetch(url, { method: req.method, headers, body, redirect: 'manual' })

  const respHeaders = new Headers(resp.headers)
  // strip hop-by-hop headers
  ['connection','keep-alive','transfer-encoding','upgrade'].forEach(h => respHeaders.delete(h))

  const respBody = await resp.arrayBuffer()
  return new NextResponse(respBody && respBody.byteLength ? Buffer.from(respBody) : null, {
    status: resp.status,
    headers: respHeaders as any,
  })
}

export async function GET(req: NextRequest, { params }: { params: any }) { return forward(req, params) }
export async function POST(req: NextRequest, { params }: { params: any }) { return forward(req, params) }
export async function PUT(req: NextRequest, { params }: { params: any }) { return forward(req, params) }
export async function PATCH(req: NextRequest, { params }: { params: any }) { return forward(req, params) }
export async function DELETE(req: NextRequest, { params }: { params: any }) { return forward(req, params) }
export async function OPTIONS(req: NextRequest, { params }: { params: any }) { return forward(req, params) }
