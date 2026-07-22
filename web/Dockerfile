# Dev image only: the dev server runs here; prod ships a static `dist/` built in CI (see ROADMAP §17).
# Debian slim (glibc) matches CI's ubuntu runner, so one lockfile satisfies `npm ci` in both.
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
