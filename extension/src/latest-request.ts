export class LatestRequestGuard {
  private generation = 0;

  begin(): number { return ++this.generation; }
  invalidate(): void { this.generation += 1; }
  isCurrent(requestGeneration: number): boolean { return requestGeneration === this.generation; }
}
