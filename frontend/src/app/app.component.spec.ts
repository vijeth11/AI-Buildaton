import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AppComponent } from './app.component';
import { ClaimRecord } from './core/claim.types';
import { demoAuthInterceptor } from './core/demo-auth.interceptor';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideHttpClient(withInterceptors([demoAuthInterceptor])), provideHttpClientTesting()],
    }).compileComponents();
  });

  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('filters and searches by claim route and policy data', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    app.claims = [
      { claim_id: 'CLM-A', policy_number: 'DIC-PC-0001', route_category: 'investigate' } as ClaimRecord,
      { claim_id: 'CLM-B', policy_number: 'DIC-PC-0002', route_category: 'fast_tracked' } as ClaimRecord,
    ];
    app.selectedFilter = 'investigate';
    expect(app.visibleClaims.map((claim) => claim.claim_id)).toEqual(['CLM-A']);
    app.searchTerm = 'DIC-PC-0002';
    app.searchClaims();
    expect(app.visibleClaims).toEqual([]);
  });

  it('loads and renders the claims work queue', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('http://127.0.0.1:8000/api/auth/login').flush({
      access_token: 'signed-demo-test-token',
      token_type: 'bearer',
      expires_in: 3600,
      username: 'adjuster.demo',
      role: 'adjuster',
    });
    const claimsRequest = http.expectOne('http://127.0.0.1:8000/api/claims');
    expect(claimsRequest.request.headers.get('Authorization')).toBe('Bearer signed-demo-test-token');
    claimsRequest.flush([]);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Claims Work Queue');
    expect(compiled.textContent).toContain('No claims in this view.');
    expect(compiled.querySelector('[aria-label="Report a claim"]')).toBeTruthy();
  });
});
