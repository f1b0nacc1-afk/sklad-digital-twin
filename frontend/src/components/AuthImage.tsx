import { Image, Skeleton } from 'antd'
import { useEffect, useState } from 'react'
import { tokenStore } from '../api/client'

interface Props {
  src: string
  alt: string
  width?: number | string
  preview?: boolean
}

interface Loaded {
  src: string
  url: string | null
}

export default function AuthImage({ src, alt, width = '100%', preview = true }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    const token = tokenStore.get()
    fetch(src, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setLoaded({ src, url: objectUrl })
      })
      .catch(() => !cancelled && setLoaded({ src, url: null }))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src])

  if (loaded?.src !== src) return <Skeleton.Image active style={{ width: '100%', height: 240 }} />
  if (!loaded.url) return <div style={{ color: '#999' }}>Изображение недоступно</div>
  return <Image src={loaded.url} alt={alt} width={width} preview={preview} />
}
