FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Omgevingsindicator (#145): build-time ingebakken (NEXT_PUBLIC_* wordt door Next
# bij de build geïnlined). Per omgeving gezet via de compose-build-args.
ARG NEXT_PUBLIC_APP_ENV=prod
ARG NEXT_PUBLIC_ENV_COLOR=
ENV NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV
ENV NEXT_PUBLIC_ENV_COLOR=$NEXT_PUBLIC_ENV_COLOR
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
