import { useParams } from 'react-router-dom'
import PlaceholderPage from '../components/PlaceholderPage'

export default function PublicLeaguePage() {
  const { slug } = useParams<{ slug: string }>()
  return <PlaceholderPage title={`League — ${slug}`} />
}
