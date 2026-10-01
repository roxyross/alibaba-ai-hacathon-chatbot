# Multi-stage Dockerfile for Vite React 18 Frontend
FROM node:20-alpine AS base
WORKDIR /app

# Install dependencies layer
COPY package.json package-lock.json ./
RUN npm ci

# Stage 2: Development with hot reload
FROM base AS development
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# Stage 3: Builder for production assets
FROM base AS builder
COPY . .
RUN npm run build

# Stage 4: Production Nginx server
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
