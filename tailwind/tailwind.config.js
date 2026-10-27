/** @type {import('tailwindcss').Config} */
module.exports = {
  // Paths are relative to the repo root (where the CLI is run). Only full class
  // names written out in these files end up in the CSS — never build them by
  // concatenation (e.g. 'bg-' + colour).
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        amber: { 500: "#f59e0b" },
      },
    },
  },
};
