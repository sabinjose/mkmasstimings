export type Bucket = "mass" | "confession" | "adoration";

export interface RawService {
  date?: string | null;
  day?: string;
  time?: string | null;
  type?: string;
  church?: string | null;
  church_location?: string | null;
  area?: string;
  postcode?: string;
  language?: string | null;
  cancelled?: boolean;
  notes?: string | null;
}

export interface RawParish {
  parish: string;
  location?: string;
  source_url?: string;
  outside_mk?: boolean;
  error?: string;
  services?: RawService[];
}

export interface RawData {
  generated_at?: string;
  parishes: RawParish[];
}

export interface Service extends RawService {
  parish: string;
  location: string;
  source_url: string;
  outside_mk: boolean;
  parish_key: string;
  bucket: Bucket;
  cancelled: boolean;
}
