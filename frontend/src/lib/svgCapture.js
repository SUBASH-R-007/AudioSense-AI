// Serialize the audiogram's SVG to a base64 PNG for the PDF report.
export async function captureSvgAsPng(container, scale = 2) {
  const svg = container?.querySelector('svg')
  if (!svg) return null
  const clone = svg.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const { width, height } = svg.getBoundingClientRect()
  clone.setAttribute('width', width)
  clone.setAttribute('height', height)
  const blob = new Blob([new XMLSerializer().serializeToString(clone)],
    { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image()
      i.onload = () => resolve(i)
      i.onerror = reject
      i.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png')
  } finally {
    URL.revokeObjectURL(url)
  }
}
