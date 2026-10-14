// import './Auth.css'
// import { useState } from 'react'
// import { supabase } from '../library/supabase'

// function Auth() {
//   const [isLogin, setIsLogin] = useState(true)
//   const [email, setEmail] = useState('')
//   const [password, setPassword] = useState('')
//   const [loading, setLoading] = useState(false)
//   const [error, setError] = useState('')
//   const [message, setMessage] = useState('')

//   async function handleSubmit(event) {
//     event.preventDefault()
//     setError('')
//     setMessage('')
//     setLoading(true)

//     try {
//       if (isLogin) {
//         const { error } = await supabase.auth.signInWithPassword({
//           email,
//           password,
//         })

//         if (error) throw error
//       } else {
//         const { data, error } = await supabase.auth.signUp({
//           email,
//           password,
//           options: {
//             emailRedirectTo: window.location.origin,
//           },
//         })

//         if (error) throw error

//         if (!data.session) {
//           setMessage('Check your email to confirm your account.')
//         } else {
//           setMessage('Account created successfully.')
//         }
//       }
//     } catch (error) {
//       setError(error.message || 'Authentication failed.')
//     } finally {
//       setLoading(false)
//     }
//   }

//   return (
//     <div className="auth-page">
//       <form className="auth-card" onSubmit={handleSubmit}>
//         <h1>MultiMind</h1>
//         <p>{isLogin ? 'Welcome back' : 'Create your account'}</p>

//         <label htmlFor="auth-email">Email</label>
//         <input
//           id="auth-email"
//           type="email"
//           value={email}
//           onChange={(event) => setEmail(event.target.value)}
//           autoComplete="email"
//           required
//         />

//         <label htmlFor="auth-password">Password</label>
//         <input
//           id="auth-password"
//           type="password"
//           value={password}
//           onChange={(event) => setPassword(event.target.value)}
//           autoComplete={isLogin ? 'current-password' : 'new-password'}
//           minLength={8}
//           required
//         />

//         {error && <p role="alert">{error}</p>}
//         {message && <p role="status">{message}</p>}

//         <button type="submit" disabled={loading}>
//           {loading
//             ? 'Please wait...'
//             : isLogin
//               ? 'Log in'
//               : 'Create account'}
//         </button>

//         <button
//           type="button"
//           onClick={() => {
//             setIsLogin((current) => !current)
//             setError('')
//             setMessage('')
//           }}
//         >
//           {isLogin
//             ? 'Need an account? Sign up'
//             : 'Already have an account? Log in'}
//         </button>
//       </form>
//     </div>
//   )
// }

// export default Auth


import './Auth.css'
import { useState } from 'react'
import { supabase } from '../library/supabase'

const APP_URL = 'https://multi-mind-steel.vercel.app'

function Auth() {
  const [isLogin, setIsLogin] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)

    try {
      const cleanEmail = email.trim().toLowerCase()

      if (isLogin) {
        const { error } = await supabase.auth.signInWithPassword({
          email: cleanEmail,
          password,
        })

        if (error) throw error

        // Successful login: App.jsx observes the Supabase session.
        setMessage('Login successful. Opening MultiMind...')
      } else {
        const { data, error } = await supabase.auth.signUp({
          email: cleanEmail,
          password,
          options: {
            emailRedirectTo: `${APP_URL}/`,
          },
        })

        if (error) throw error

        if (data.session) {
          setMessage('Account created successfully. Opening MultiMind...')
        } else {
          setMessage(
            'Account created! Please confirm your email using the latest confirmation link.'
          )
        }
      }
    } catch (error) {
      setError(error.message || 'Authentication failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>MultiMind</h1>
        <p>{isLogin ? 'Welcome back' : 'Create your account'}</p>

        <label htmlFor="auth-email">Email</label>
        <input
          id="auth-email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          autoComplete="email"
          required
        />

        <label htmlFor="auth-password">Password</label>
        <input
          id="auth-password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete={isLogin ? 'current-password' : 'new-password'}
          minLength={8}
          required
        />

        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}

        <button type="submit" disabled={loading}>
          {loading
            ? 'Please wait...'
            : isLogin
              ? 'Log in'
              : 'Create account'}
        </button>

        <button
          type="button"
          disabled={loading}
          onClick={() => {
            setIsLogin((current) => !current)
            setError('')
            setMessage('')
          }}
        >
          {isLogin
            ? 'Need an account? Sign up'
            : 'Already have an account? Log in'}
        </button>
      </form>
    </div>
  )
}

export default Auth