# Stage 1: deps — clone agent-chat-ui and install
FROM node:20-alpine AS deps
WORKDIR /app
RUN apk add --no-cache git
RUN npm install -g pnpm
RUN git clone --depth 1 https://github.com/langchain-ai/agent-chat-ui.git .
RUN pnpm install --frozen-lockfile

# Stage 2: build — bake env vars at build time
FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm
COPY --from=deps /app ./
# Browser accesses LangGraph server via host-mapped port
ARG NEXT_PUBLIC_API_URL=http://localhost:2024
ARG NEXT_PUBLIC_ASSISTANT_ID=coordinator
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_ASSISTANT_ID=$NEXT_PUBLIC_ASSISTANT_ID
RUN pnpm run build

# Stage 3: runner
FROM node:20-alpine AS runner
WORKDIR /app
RUN npm install -g pnpm
ENV NODE_ENV=production
COPY --from=builder /app ./
EXPOSE 3000
CMD ["pnpm", "start"]
