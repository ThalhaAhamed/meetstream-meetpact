import { UserRound } from 'lucide-react'
import { api } from '../api'
import { Card, Empty, ErrorBox, Spinner, useLoad } from '../components/ui'
import { ProfileView } from './EmployeeProfile'

export default function MyProgress() {
  const { data, error, loading, reload } = useLoad(() => api.myDashboard(), [])
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Spinner />
  if (!data.employee) {
    return (
      <Card><Empty icon={UserRound} title="Your login is not linked to an employee profile">
        Ask an admin to link your user to your employee record under Admin → Users, so your meeting updates show up here.
      </Empty></Card>
    )
  }
  return <ProfileView data={data} reload={reload} isSelf />
}
