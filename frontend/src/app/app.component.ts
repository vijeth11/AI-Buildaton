import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { ClaimRecord, ClaimSubmission, Metrics, PolicySummary } from './core/claim.types';
import { ClaimsApiService } from './core/claims-api.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent implements OnInit {
  readonly api = inject(ClaimsApiService);

  claims: ClaimRecord[] = [];
  selectedClaim: ClaimRecord | null = null;
  metrics: Metrics | null = null;
  activeView: 'queue' | 'review' | 'metrics' | 'intake' = 'queue';
  selectedFilter = 'all';
  searchTerm = '';
  appliedSearchTerm = '';
  metricsPeriod: 'today' | 'last_7_days' = 'today';
  reviewerId = 'reviewer.demo';
  currentDemoIdentity: 'claims.agent' | 'adjuster.demo' | 'supervisor.demo' | 'admin.demo' = 'adjuster.demo';
  decisionReason = '';
  modifiedAmount = 0;
  additionalEvidenceKind = 'incident_report';
  additionalEvidenceText = '';
  errorMessage = '';
  successMessage = '';
  busy = false;
  policyNumber = '';
  policyLookup: PolicySummary | null = null;
  photoFiles: File[] = [];
  documentFiles: File[] = [];
  draftClaimId: string | null = null;
  form: ClaimSubmission = this.emptyForm();

  ngOnInit(): void {
    this.loginDemoIdentity(this.currentDemoIdentity);
  }

  loginDemoIdentity(username: 'claims.agent' | 'adjuster.demo' | 'supervisor.demo' | 'admin.demo'): void {
    this.currentDemoIdentity = username;
    this.busy = true;
    this.api.loginDemo(username).subscribe({
      next: (session) => {
        globalThis.localStorage?.setItem('claims-demo-token', session.access_token);
        this.reviewerId = session.username;
        this.refresh();
      },
      error: () => {
        this.errorMessage = 'Local development login failed. Check the API role stub and retry.';
        this.busy = false;
      },
    });
  }

  get visibleClaims(): ClaimRecord[] {
    const query = this.appliedSearchTerm.trim().toLowerCase();
    return this.claims.filter((claim) => {
      const matchesRoute = this.selectedFilter === 'all' || (claim.route_category || 'human_queue') === this.selectedFilter;
      const matchesQuery = !query || [claim.claim_id, claim.policy_number, claim.claimant_name, claim.vehicle_registration]
        .some((value) => value?.toLowerCase().includes(query));
      return matchesRoute && matchesQuery;
    });
  }

  get routeCounts(): Record<string, number> {
    return this.claims.reduce<Record<string, number>>((counts, claim) => {
      const route = claim.route_category || 'human_queue';
      counts[route] = (counts[route] || 0) + 1;
      return counts;
    }, {});
  }

  selectView(view: 'queue' | 'review' | 'metrics' | 'intake'): void {
    this.activeView = view;
    this.clearMessages();
    if (view === 'metrics') this.loadMetrics();
    if (view === 'queue') this.refresh();
    if (view === 'intake') this.resetIntake();
  }

  refresh(): void {
    this.busy = true;
    this.api.getClaims().subscribe({
      next: (claims) => {
        this.claims = claims;
        this.busy = false;
        if (this.selectedClaim) this.loadClaim(this.selectedClaim.claim_id);
      },
      error: () => {
        this.errorMessage = 'Could not reach the claims API. Start the backend and refresh.';
        this.busy = false;
      },
    });
  }

  openClaim(claim: ClaimRecord): void {
    this.activeView = 'review';
    this.selectedClaim = claim;
    this.loadClaim(claim.claim_id);
  }

  loadClaim(claimId: string): void {
    this.api.getClaim(claimId).subscribe({
      next: (claim) => (this.selectedClaim = claim),
      error: () => (this.errorMessage = 'Claim detail could not be loaded.'),
    });
  }

  lookupPolicy(): void {
    this.clearMessages();
    this.policyLookup = null;
    this.api.getPolicy(this.policyNumber.trim()).subscribe({
      next: (policy) => {
        this.policyLookup = policy;
        this.form = { ...this.form, policy_number: policy.policy_number };
        this.successMessage = 'Active synthetic policy found.';
      },
      error: () => (this.errorMessage = 'No active policy was found. Check the policy number.'),
    });
  }

  onPhotoSelection(event: Event): void {
    const input = event.target as HTMLInputElement;
    const selected = Array.from(input.files || []);
    if (selected.length > 3) {
      this.errorMessage = 'Select no more than three car photos.';
      input.value = '';
      return;
    }
    this.photoFiles = selected;
    this.clearMessages();
  }

  onDocumentSelection(event: Event): void {
    const input = event.target as HTMLInputElement;
    const selected = Array.from(input.files || []);
    if (selected.length > 10) {
      this.errorMessage = 'Select no more than ten supporting documents.';
      input.value = '';
      return;
    }
    this.documentFiles = selected;
    this.clearMessages();
  }

  async submitClaim(): Promise<void> {
    if (!this.policyLookup) {
      this.errorMessage = 'Look up an active policy before submitting the claim.';
      return;
    }
    this.busy = true;
    this.clearMessages();
    try {
      if (!this.draftClaimId) {
        const draft = await firstValueFrom(this.api.createDraft(this.form));
        this.draftClaimId = draft.claim_id;
      }
      if (this.photoFiles.length) {
        await firstValueFrom(this.api.uploadPhotos(this.draftClaimId, this.photoFiles));
      }
      if (this.documentFiles.length) {
        await firstValueFrom(this.api.uploadDocuments(this.draftClaimId, this.documentFiles));
      }
      const claim = await firstValueFrom(this.api.submitDraft(this.draftClaimId));
      this.selectedClaim = claim;
      this.successMessage = `Claim ${claim.claim_id} submitted. Route: ${this.label(claim.route_category || claim.status)}.`;
      this.draftClaimId = null;
      this.photoFiles = [];
      this.documentFiles = [];
      this.activeView = 'review';
      this.refresh();
    } catch {
      this.errorMessage = 'Claim submission did not complete. The draft remains available; retry after correcting the issue.';
      this.busy = false;
    }
  }

  decide(action: 'approve' | 'decline' | 'investigate' | 'request_evidence' | 'modify'): void {
    if (!this.selectedClaim || this.decisionReason.trim().length < 3) return;
    if (action === 'modify' && this.modifiedAmount <= 0) return;
    this.busy = true;
    this.api.recordDecision(
      this.selectedClaim.claim_id,
      action,
      this.reviewerId,
      this.decisionReason,
      action === 'modify' ? this.modifiedAmount : undefined,
    ).subscribe({
      next: (claim) => {
        this.selectedClaim = claim;
        this.successMessage = `Reviewer action recorded: ${this.label(action)}.`;
        this.decisionReason = '';
        this.refresh();
      },
      error: () => {
        this.errorMessage = 'Reviewer action was not accepted. Confirm the claim is in the review queue.';
        this.busy = false;
      },
    });
  }

  provideRequestedEvidence(): void {
    if (!this.selectedClaim || this.additionalEvidenceText.trim().length < 5) return;
    this.busy = true;
    this.api.submitAdditionalEvidence(this.selectedClaim.claim_id, this.additionalEvidenceKind, this.additionalEvidenceText).subscribe({
      next: (claim) => {
        this.selectedClaim = claim;
        this.additionalEvidenceText = '';
        this.successMessage = 'Additional evidence stored and the claim was re-evaluated.';
        this.refresh();
      },
      error: () => {
        this.errorMessage = 'Additional evidence was not accepted. Confirm the claim is awaiting evidence.';
        this.busy = false;
      },
    });
  }

  loadMetrics(): void {
    this.api.getMetricsFor(this.metricsPeriod).subscribe({
      next: (metrics) => (this.metrics = metrics),
      error: () => (this.errorMessage = 'AgentOps metrics could not be loaded.'),
    });
  }

  label(value: string): string {
    return value.replaceAll('_', ' ');
  }

  claimAge(claim: ClaimRecord): string {
    if (!claim.created_at) return '—';
    const ageMinutes = Math.max(0, Math.floor((Date.now() - new Date(claim.created_at).getTime()) / 60000));
    if (ageMinutes < 60) return `${ageMinutes}m`;
    if (ageMinutes < 1440) return `${Math.floor(ageMinutes / 60)}h`;
    return `${Math.floor(ageMinutes / 1440)}d`;
  }

  routeReason(claim: ClaimRecord): string {
    switch (claim.route_category) {
      case 'needs_approval':
        return `The garage estimate exceeds the configured INR 50,000 auto-settlement limit. Agents cannot pay this claim without a reviewer.`;
      case 'investigate':
        return `The fraud score is ${claim.adjudication?.fraud_score ?? 'unavailable'} against a threshold of ${claim.adjudication?.fraud_threshold ?? 'unavailable'}. Review the evidence before deciding.`;
      case 'supervisor_review':
        return `High-risk or severe-amount claim. Risk ${claim.adjudication?.risk_score ?? 'unavailable'}, fraud ${claim.adjudication?.fraud_score ?? 'unavailable'}, amount ${claim.requested_amount}. Supervisor approval is required.`;
      case 'fast_tracked':
        return 'The deterministic eligibility checks passed and both scores were below threshold. A synthetic test-mode payout was recorded.';
      default:
        return `The agent workflow routed this claim for review: ${claim.adjudication?.review_flags.join(', ') || 'an eligibility check needs confirmation'}.`;
    }
  }

  searchClaims(): void {
    this.appliedSearchTerm = this.searchTerm;
  }

  recommendedPayout(claim: ClaimRecord): number {
    return claim.adjudication?.settlement_calculations.find((item) => item.operation === 'result')?.amount || 0;
  }

  tokenBar(tokens: number): number {
    const maximum = Math.max(1, ...(this.metrics?.agent_performance.map((agent) => agent.average_tokens) || [1]));
    return Math.max(1, (tokens / maximum) * 100);
  }

  private clearMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private resetIntake(): void {
    this.policyNumber = '';
    this.policyLookup = null;
    this.photoFiles = [];
    this.documentFiles = [];
    this.draftClaimId = null;
    this.form = this.emptyForm();
  }

  private emptyForm(): ClaimSubmission {
    return {
      policy_number: 'POL-AUTO-100',
      loss_type: 'flood',
      loss_description: '',
      incident_date: new Date().toISOString().slice(0, 10),
      incident_pincode: '',
      incident_location: '',
      garage_estimate: 140000,
      currency: 'INR',
      fictional: true,
    };
  }
}
