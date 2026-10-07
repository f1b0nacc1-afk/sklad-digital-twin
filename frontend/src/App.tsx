import {
  AppstoreOutlined,
  BarChartOutlined,
  CameraOutlined,
  HistoryOutlined,
  LogoutOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Button, Layout, Menu, Result, Space, Spin, Typography } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import LoginPage from './pages/LoginPage'
import TwinPage from './pages/TwinPage'

const ROLE_LABEL = { admin: 'Администратор', operator: 'Оператор', viewer: 'Наблюдатель' }

const MENU = [
  { key: '/twin', icon: <AppstoreOutlined />, label: 'Цифровой двойник' },
  { key: '/scans', icon: <CameraOutlined />, label: 'Сканирования' },
  { key: '/objects', icon: <SearchOutlined />, label: 'Объекты' },
  { key: '/events', icon: <HistoryOutlined />, label: 'История' },
  { key: '/reports', icon: <BarChartOutlined />, label: 'Отчёты' },
  { key: '/admin', icon: <SettingOutlined />, label: 'Администрирование', adminOnly: true },
]

function NotReady() {
  return <Result status="info" title="Раздел в разработке" subTitle="См. план реализации" />
}

export default function App() {
  const { user, loading, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  if (loading) return <Spin fullscreen />
  if (!user) return <LoginPage />

  const items = MENU.filter((m) => !m.adminOnly || user.role === 'admin').map(
    ({ key, icon, label }) => ({ key, icon, label }),
  )

  return (
    <Layout style={{ height: '100%' }}>
      <Layout.Sider width={230} theme="light" breakpoint="lg" collapsible>
        <div style={{ padding: '16px 20px', fontWeight: 600 }}>Цифровой двойник склада</div>
        <Menu
          mode="inline"
          selectedKeys={['/' + location.pathname.split('/')[1]]}
          items={items}
          onClick={(e) => navigate(e.key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{ background: '#fff', display: 'flex', justifyContent: 'flex-end', paddingInline: 24 }}
        >
          <Space>
            <Typography.Text>
              {user.full_name || user.login} · {ROLE_LABEL[user.role]}
            </Typography.Text>
            <Button icon={<LogoutOutlined />} onClick={logout}>
              Выйти
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content style={{ padding: 16, overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<Navigate to="/twin" replace />} />
            <Route path="/twin" element={<TwinPage />} />
            <Route path="*" element={<NotReady />} />
          </Routes>
        </Layout.Content>
      </Layout>
    </Layout>
  )
}
