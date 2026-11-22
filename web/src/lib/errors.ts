export class ApiError extends Error {
  field?: "service" | "location";
  suggestions: string[];
  constructor(message: string, field?: "service" | "location", suggestions: string[] = []) {
    super(message);
    this.field = field;
    this.suggestions = suggestions;
  }
}
