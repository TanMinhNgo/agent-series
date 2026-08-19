import { Phone, X } from 'lucide-react';
import { useState } from 'react';
import { siGoogle } from 'simple-icons';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/src/hooks/use-auth';

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 shrink-0">
      <path fill={`#${siGoogle.hex}`} d={siGoogle.path} />
    </svg>
  );
}

export function LoginPage() {
  const { startGoogleSignIn } = useAuth();
  const [email, setEmail] = useState('');
  const authError = new URLSearchParams(window.location.search).get('authError');
  const startSignIn = () => {
    const returnTo = `${window.location.pathname}${window.location.search}`;
    if (returnTo !== '/' && !returnTo.startsWith('/login'))
      sessionStorage.setItem('agent-series.auth-return-to', returnTo);
    startGoogleSignIn(email);
  };

  return (
    <main className="grid min-h-dvh place-items-center bg-background p-4 text-foreground sm:p-6">
      <section className="relative w-full max-w-md rounded-[1.25rem] border border-border bg-card px-10 py-9 shadow-2xl sm:px-[2.6rem]">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute right-5 top-5 text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={() => window.history.back()}
          aria-label="Đóng đăng nhập"
        >
          <X className="size-4.5" />
        </Button>

        <header className="pr-5 text-center">
          <h1 className="text-[1.35rem] font-semibold tracking-[-0.02em]">Đăng nhập hoặc đăng ký</h1>
          <p className="mx-auto mt-3 max-w-[20rem] text-sm leading-5 text-muted-foreground">
            Bạn sẽ nhận được phản hồi thông minh hơn và có thể tải lên tệp, hình ảnh, v.v.
          </p>
        </header>

        <div className="mt-7 grid gap-3">
          <Button
            type="button"
            className="h-12 w-full rounded-full bg-primary text-[0.95rem] font-semibold text-primary-foreground hover:bg-primary/85"
            onClick={() => startSignIn()}
          >
            <GoogleIcon />
            Tiếp tục với Google
          </Button>
          <Button
            type="button"
            disabled
            title="Đăng nhập số điện thoại đang được phát triển"
            className="h-12 w-full rounded-full bg-primary text-[0.95rem] font-semibold text-primary-foreground disabled:opacity-100"
          >
            <Phone className="size-4.5" />
            Tiếp tục với số điện thoại
          </Button>
        </div>

        <div className="my-6 flex items-center gap-4 text-xs font-medium text-muted-foreground">
          <span className="h-px flex-1 bg-border" />
          HOẶC
          <span className="h-px flex-1 bg-border" />
        </div>

        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            startSignIn();
          }}
        >
          <input
            className="h-12 w-full rounded-full border border-input bg-background px-4 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Địa chỉ email"
          />
          <Button
            type="submit"
            className="h-12 w-full rounded-full bg-primary text-[0.95rem] font-semibold text-primary-foreground hover:bg-primary/85"
          >
            Tiếp tục
          </Button>
        </form>
        <p className="mt-3 text-center text-xs leading-5 text-muted-foreground">
          Email sẽ được dùng để gợi ý tài khoản trong bước Google tiếp theo.
        </p>
        {authError ? (
          <p role="alert" className="mt-3 text-center text-sm text-destructive">
            {authError}
          </p>
        ) : null}
      </section>
    </main>
  );
}
