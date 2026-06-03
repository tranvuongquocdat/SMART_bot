import { QueryClient } from '@tanstack/react-query';
import { redirect } from 'react-router-dom';
import type { LoaderFunction } from 'react-router-dom';
import { ApiError } from './api';
import { meQuery } from './auth';
import type { Me, Role } from './auth';

export function defaultHomeFor(me: Me): string {
  return me.roles.includes('superadmin')
    ? '/app/superadmin/models'
    : '/app/admin/dashboard';
}

export function requireRole(role: Role, qc: QueryClient): LoaderFunction {
  return async () => {
    let me: Me;
    try {
      me = await qc.fetchQuery(meQuery);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        throw redirect('/login');
      }
      throw e;
    }
    if (!me.roles.includes(role)) {
      throw redirect(defaultHomeFor(me));
    }
    return me;
  };
}

export function requireAuth(qc: QueryClient): LoaderFunction {
  return async () => {
    try {
      const me = await qc.fetchQuery(meQuery);
      throw redirect(defaultHomeFor(me));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        throw redirect('/login');
      }
      throw e;
    }
  };
}
