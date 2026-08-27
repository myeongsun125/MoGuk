import ko from "./ko/messages.json";
import vi from "./vi/messages.json";
import id from "./in/messages.json";
import type { Lang } from "../api/types";

export const MESSAGES: Record<Lang, Record<string, string>> = { ko, vi, in: id };
