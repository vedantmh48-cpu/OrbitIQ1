import "./shim.mjs";
import { setStateOverride } from "./zustand-shim.mjs";
const React = (await import("react")).default;
const { renderToStaticMarkup } = await import("react-dom/server");
const { MemoryRouter } = await import("react-router-dom");
const { default: Login } = await import("../src/pages/Login.jsx");
const { useAuthStore } = await import("../src/store/authStore.ts");

setStateOverride(() => ({ user: null, booting: false, loading: false }));
const html = renderToStaticMarkup(
  React.createElement(MemoryRouter, { initialEntries: ["/"] }, React.createElement(Login, null))
);
for (const m of html.matchAll(/<input[^>]*>/g)) console.log(m[0], "\n");
console.log("form tag:", (html.match(/<form[^>]*>/) || [""])[0]);
console.log("register link:", (html.match(/<a[^>]*register[^>]*>/) || [""])[0]);
