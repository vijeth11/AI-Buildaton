import { HttpInterceptorFn } from '@angular/common/http';

const SESSION_KEY = 'claims-demo-token';

export const demoAuthInterceptor: HttpInterceptorFn = (request, next) => {
  if (request.url.endsWith('/api/auth/login')) return next(request);
  const token = globalThis.localStorage?.getItem(SESSION_KEY);
  return next(token ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : request);
};
