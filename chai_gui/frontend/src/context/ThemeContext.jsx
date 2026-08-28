import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext()

export function ThemeProvider({ children }) {

    // Default is always Light for a first-time visitor (e.g. landing on the
    // login page with no prior session). Once the user picks a theme, that
    // choice is persisted in localStorage and restored on every later visit.
    const [theme, setTheme] = useState(
        localStorage.getItem('theme') || 'light'
    )

    useEffect(() => {

        document.documentElement.classList.remove('light', 'dark')
        document.documentElement.classList.add(theme)

        localStorage.setItem('theme', theme)

    }, [theme])

    return (
        <ThemeContext.Provider value={{ theme, setTheme }}>
            {children}
        </ThemeContext.Provider>
    )
}

export const useTheme = () => useContext(ThemeContext)
