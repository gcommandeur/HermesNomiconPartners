FROM node:22-slim AS base
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Wird zur Build-Zeit in den Client-Bundle eingebacken - muss beim Docker-Build
# als --build-arg gesetzt werden (siehe DEPLOYMENT.md).
ARG NEXT_PUBLIC_CC_CRM_API_URL
ENV NEXT_PUBLIC_CC_CRM_API_URL=$NEXT_PUBLIC_CC_CRM_API_URL
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# node:22-slim already ships an unprivileged "node" user (uid/gid 1000) -
# run as that instead of root in the final image.
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node

EXPOSE 3000
CMD ["node", "server.js"]
