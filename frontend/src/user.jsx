import { createContext, useContext } from 'react'

export const UserContext = createContext({ user: null, setUser: () => {} })
export const useUser = () => useContext(UserContext).user
export const useSetUser = () => useContext(UserContext).setUser
export const isManager = (u) => u && (u.role === 'admin' || u.role === 'manager')
