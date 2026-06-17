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
# Umami web-analytics (#152, laag 1) — leeg laat de tracker niet laden (no-op).
ARG NEXT_PUBLIC_UMAMI_SRC=
ARG NEXT_PUBLIC_UMAMI_WEBSITE_ID=
ENV NEXT_PUBLIC_UMAMI_SRC=$NEXT_PUBLIC_UMAMI_SRC
ENV NEXT_PUBLIC_UMAMI_WEBSITE_ID=$NEXT_PUBLIC_UMAMI_WEBSITE_ID
# Chatbot 'Raakje' (#205) — hoofdschakelaar, build-time ingebakken (#239). Zonder
# deze ARG dropt Docker de compose-build-arg stil en blijft de widget verborgen.
ARG NEXT_PUBLIC_CHATBOT_ENABLED=false
ENV NEXT_PUBLIC_CHATBOT_ENABLED=$NEXT_PUBLIC_CHATBOT_ENABLED
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
