# Development image: Vite dev server with hot reload. Production serves the static build from S3.
FROM node:24-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
