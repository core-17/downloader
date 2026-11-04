# SSL Сертифікати для Nginx

У цій папці зберігаються SSL-сертифікати для HTTPS (порт 443):

- `selfsigned.crt` — публічний сертифікат (за замовчуванням згенеровано самопідписаний для `localhost`).
- `selfsigned.key` — приватний ключ.

## Використання власних сертифікатів (Let's Encrypt / Cloudflare / Custom)
Якщо у вас є власний сертифікат для домену (наприклад, від Certbot):
1. Скопіюйте `fullchain.pem` сюди та назвіть його `selfsigned.crt` (або створіть симлінк).
2. Скопіюйте `privkey.pem` сюди та назвіть його `selfsigned.key`.
3. Перезавантажте проксі: `docker compose restart proxy`.
