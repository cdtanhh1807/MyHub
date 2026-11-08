// ID bền vững theo browser/profile và origin; không chứa token, không thay thế đăng nhập.
const key = 'myhub.device';
let current = localStorage.getItem(key);
if (!current || !/^[A-Za-z0-9_-]{1,80}$/.test(current)) {
  current = crypto.randomUUID();
  localStorage.setItem(key, current);
}
export const deviceId = current;
