FROM node:22-slim

ENV NODE_ENV=development \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer (package-lock.json is optional in this scaffold)
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:3000/ || exit 1

CMD ["npm", "run", "dev"]
