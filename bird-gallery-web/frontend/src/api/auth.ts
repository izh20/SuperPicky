import client from './client'

export interface LoginResponse {
  token: string
  username: string
  role: string
}

export interface UserInfo {
  username: string
  user_id: string
  role: string
}

export interface UserItem {
  id: string
  username: string
  role: string
  created_at: string
}

const authAPI = {
  login: (username: string, password: string): Promise<LoginResponse> =>
    client.post('/auth/login', { username, password }),

  me: (): Promise<UserInfo> => client.get('/auth/me'),

  changePassword: (old_password: string, new_password: string): Promise<{ message: string }> =>
    client.post('/auth/password', { old_password, new_password }),

  register: (username: string, password: string, role = 'user'): Promise<{ id: string; username: string; role: string }> =>
    client.post('/auth/register', { username, password, role }),

  listUsers: (): Promise<{ users: UserItem[] }> => client.get('/auth/users'),

  deleteUser: (userId: string): Promise<{ message: string }> =>
    client.delete(`/auth/users/${userId}`),
}

export default authAPI
