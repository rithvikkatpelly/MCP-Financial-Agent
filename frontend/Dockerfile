# syntax=docker/dockerfile:1
#
# Static build of the Econ Data frontend, served by nginx.
# Build context is frontend/:
#
#   docker build -f frontend/Dockerfile \
#     --build-arg VITE_API_BASE_URL=https://your-api.example.com \
#     -t econ-data-frontend ./frontend
#
# VITE_API_BASE_URL is inlined at build time, so the API's URL must be known
# before `npm run build` runs — pass it as a --build-arg once the backend is
# deployed.

# --- Build the Vite bundle ---
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# --- Serve it ---
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
