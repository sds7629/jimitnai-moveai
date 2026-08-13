FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

EXPOSE 5173

# --host 0.0.0.0 없이는 컨테이너 밖(호스트 브라우저)에서 Vite 개발 서버에 접속할 수 없다.
# 볼륨 마운트+bind mount(docker-compose.yml)로 소스를 살아있게 유지해 HMR이 그대로 동작한다.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
