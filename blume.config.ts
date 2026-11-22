import { defineConfig } from "blume";

export default defineConfig({
  title: "tabledoc",
  description: "Makes the tables of a dataset readable by people and AI",
  logo: "/icon.svg",
  theme: {
    accent: "#7846be",
  },
  deployment: {
    site: "https://tabledoc.queria.io",
  },
  content: {
    root: "docs",
  },
  i18n: {
    defaultLocale: "en",
    locales: [
      { code: "en", label: "English" },
      { code: "ja", label: "日本語" },
    ],
  },
  seo: {
    og: {
      fonts: ["Noto Sans JP"],
    },
  },
});
