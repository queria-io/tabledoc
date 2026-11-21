import { defineConfig } from "blume";

export default defineConfig({
  title: "tabledoc",
  description: "Checks the description of a dataset and reads it for other programs",
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
