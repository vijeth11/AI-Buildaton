import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ClaimRecord, ClaimSubmission, Metrics, PolicySummary } from './claim.types';
import { environment } from '../../environments/environment';

const API_BASE_URL = environment.apiBaseUrl;

@Injectable({ providedIn: 'root' })
export class ClaimsApiService {
  private readonly http = inject(HttpClient);

  getClaims(status?: string): Observable<ClaimRecord[]> {
    let params = new HttpParams();
    if (status) params = params.set('status', status);
    return this.http.get<ClaimRecord[]>(`${API_BASE_URL}/claims`, { params });
  }

  getReviewQueue(): Observable<ClaimRecord[]> {
    return this.http.get<ClaimRecord[]>(`${API_BASE_URL}/review-queue`);
  }

  getClaim(claimId: string): Observable<ClaimRecord> {
    return this.http.get<ClaimRecord>(`${API_BASE_URL}/claims/${claimId}`);
  }

  submitClaim(claim: ClaimSubmission): Observable<ClaimRecord> {
    return this.http.post<ClaimRecord>(`${API_BASE_URL}/claims`, claim);
  }

  recordDecision(
    claimId: string,
    action: string,
    reviewerId: string,
    reason: string,
    modifiedAmount?: number,
  ): Observable<ClaimRecord> {
    return this.http.post<ClaimRecord>(`${API_BASE_URL}/claims/${claimId}/decision`, {
      action,
      reviewer_id: reviewerId,
      reason,
      ...(modifiedAmount === undefined ? {} : { modified_amount: modifiedAmount }),
    });
  }

  submitAdditionalEvidence(claimId: string, kind: string, text: string): Observable<ClaimRecord> {
    return this.http.post<ClaimRecord>(`${API_BASE_URL}/claims/${claimId}/evidence`, { kind, text });
  }

  getMetrics(): Observable<Metrics> {
    return this.http.get<Metrics>(`${API_BASE_URL}/metrics`);
  }

  getMetricsFor(period: 'today' | 'last_7_days'): Observable<Metrics> {
    return this.http.get<Metrics>(`${API_BASE_URL}/metrics`, { params: { period } });
  }

  getPolicy(policyNumber: string): Observable<PolicySummary> {
    return this.http.get<PolicySummary>(`${API_BASE_URL}/policies/${encodeURIComponent(policyNumber)}`);
  }

  createDraft(claim: ClaimSubmission): Observable<ClaimRecord> {
    return this.http.post<ClaimRecord>(`${API_BASE_URL}/claims/drafts`, claim);
  }

  uploadPhotos(claimId: string, photos: File[]): Observable<unknown> {
    const body = new FormData();
    photos.forEach((photo) => body.append('files', photo, photo.name));
    return this.http.post(`${API_BASE_URL}/claims/${claimId}/photos`, body);
  }

  uploadDocuments(claimId: string, documents: File[]): Observable<unknown> {
    const body = new FormData();
    documents.forEach((document) => body.append('files', document, document.name));
    return this.http.post(`${API_BASE_URL}/claims/${claimId}/documents`, body);
  }

  submitDraft(claimId: string): Observable<ClaimRecord> {
    return this.http.post<ClaimRecord>(`${API_BASE_URL}/claims/${claimId}/submit`, {});
  }

  photoUrl(claimId: string, photoId: string): string {
    return `${API_BASE_URL}/claims/${claimId}/photos/${photoId}`;
  }

  documentUrl(claimId: string, documentId: string): string {
    return `${API_BASE_URL}/claims/${claimId}/documents/${documentId}/file`;
  }

  loginDemo(username: 'claims.agent' | 'adjuster.demo' | 'supervisor.demo' | 'admin.demo'): Observable<DemoSession> {
    return this.http.post<DemoSession>(`${API_BASE_URL}/auth/login`, { username });
  }
}

export interface DemoSession {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  username: string;
  role: string;
}
