FROM node:22-bookworm-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 4321

CMD ["sh", "-c", "npm run preview -- --host 0.0.0.0 --port ${PORT:-4321}"]
