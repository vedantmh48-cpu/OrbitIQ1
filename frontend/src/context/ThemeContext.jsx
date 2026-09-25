import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../api/client";

const ThemeContext = createContext(null);

function applyTheme(theme) {
  if (theme === "light") {
    document.documentElement.classList.remove("dark");
    document.body.classList.add("light");
  } else {
    document.documentElement.classList.add("dark");
    document.body.classList.remove("light");
  }
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem("satquery_theme") || "dark");

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("satquery_theme", theme);
  }, [theme]);

  const setThemePreference = async (next) => {
    setTheme(next);
    try {
      await api.put("/api/users/settings", { theme: next });
    } catch {
      /* settings sync is best-effort when signed out */
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme: setThemePreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}