import cronstrue from 'cronstrue';

export interface ParsedSchedule {
  cron: string;
  description: string;
  isValid: boolean;
  isNatural: boolean;
}

const DAYS_MAP: Record<string, number> = {
  sunday: 0,
  sun: 0,
  monday: 1,
  mon: 1,
  tuesday: 2,
  tue: 2,
  tues: 2,
  wednesday: 3,
  wed: 3,
  thursday: 4,
  thu: 4,
  thur: 4,
  thurs: 4,
  friday: 5,
  fri: 5,
  saturday: 6,
  sat: 6,
};

function parseTimeStr(timeStr: string): { hour: number; minute: number } | null {
  const match = timeStr.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/i);
  if (!match) return null;

  let hour = parseInt(match[1], 10);
  const minute = match[2] ? parseInt(match[2], 10) : 0;
  const meridiem = match[3]?.toLowerCase();

  if (meridiem === 'pm' && hour < 12) hour += 12;
  if (meridiem === 'am' && hour === 12) hour = 0;

  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

/**
 * Parses user input (which may be natural language or a standard cron string)
 * into a valid 5-segment cron expression and human-readable explanation.
 */
export function parseNaturalSchedule(input: string): ParsedSchedule {
  const raw = input.trim();
  if (!raw) {
    return { cron: '', description: '', isValid: false, isNatural: false };
  }

  // 1. Check if it's already a valid 5-field cron expression
  const cronSegments = raw.split(/\s+/);
  if (cronSegments.length === 5) {
    try {
      const desc = cronstrue.toString(raw, { use24HourTimeFormat: false });
      return {
        cron: raw,
        description: desc,
        isValid: true,
        isNatural: false,
      };
    } catch {
      // Fall through to natural language check if cronstrue failed
    }
  }

  const lower = raw.toLowerCase().replace(/\s+/g, ' ');

  // 2. Natural language pattern matching

  // Pattern: "every (N) minute(s)"
  const everyNMinutes = lower.match(/^every\s+(\d+)\s*(?:min|minute)s?$/);
  if (everyNMinutes) {
    const mins = parseInt(everyNMinutes[1], 10);
    if (mins > 0 && mins <= 59) {
      const cron = `*/${mins} * * * *`;
      return {
        cron,
        description: `Every ${mins} minute${mins > 1 ? 's' : ''}`,
        isValid: true,
        isNatural: true,
      };
    }
  }

  // Pattern: "every minute"
  if (lower === 'every minute') {
    return {
      cron: '* * * * *',
      description: 'Every minute',
      isValid: true,
      isNatural: true,
    };
  }

  // Pattern: "every hour" or "hourly"
  if (lower === 'every hour' || lower === 'hourly') {
    return {
      cron: '0 * * * *',
      description: 'Every hour, on the hour',
      isValid: true,
      isNatural: true,
    };
  }

  // Pattern: "every (N) hours"
  const everyNHours = lower.match(/^every\s+(\d+)\s*(?:hour|hr)s?$/);
  if (everyNHours) {
    const hrs = parseInt(everyNHours[1], 10);
    if (hrs > 0 && hrs <= 23) {
      const cron = `0 */${hrs} * * *`;
      return {
        cron,
        description: `Every ${hrs} hours`,
        isValid: true,
        isNatural: true,
      };
    }
  }

  // Helper to extract time from strings like "at 9am", "at 9:30 pm", "at 14:00"
  const timeExtract = lower.match(/at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)/);
  const timeInfo = timeExtract ? parseTimeStr(timeExtract[1]) : { hour: 9, minute: 0 };

  if (timeInfo) {
    const { hour, minute } = timeInfo;

    // Pattern: "every weekday at ..." / "weekdays at ..." / "monday to friday at ..."
    if (lower.includes('weekday') || lower.includes('monday to friday') || lower.includes('mon-fri')) {
      const cron = `${minute} ${hour} * * 1-5`;
      const desc = cronstrue.toString(cron);
      return { cron, description: desc, isValid: true, isNatural: true };
    }

    // Pattern: "every weekend at ..." / "weekends at ..."
    if (lower.includes('weekend')) {
      const cron = `${minute} ${hour} * * 0,6`;
      const desc = cronstrue.toString(cron);
      return { cron, description: desc, isValid: true, isNatural: true };
    }

    // Pattern: "every [day of week] at ..." (e.g. "every monday at 10am")
    for (const [dayName, dayNum] of Object.entries(DAYS_MAP)) {
      if (lower.includes(dayName)) {
        const cron = `${minute} ${hour} * * ${dayNum}`;
        const desc = cronstrue.toString(cron);
        return { cron, description: desc, isValid: true, isNatural: true };
      }
    }

    // Pattern: "every day at ..." / "daily at ..." / "every morning at ..." / "every night at ..."
    if (lower.includes('every day') || lower.includes('daily') || lower.startsWith('at ') || lower.includes('morning') || lower.includes('night') || lower.includes('evening')) {
      const cron = `${minute} ${hour} * * *`;
      const desc = cronstrue.toString(cron);
      return { cron, description: desc, isValid: true, isNatural: true };
    }

    // Pattern: "every month on the 1st at ..." / "monthly at ..."
    if (lower.includes('monthly') || lower.includes('every month')) {
      const cron = `${minute} ${hour} 1 * *`;
      const desc = cronstrue.toString(cron);
      return { cron, description: desc, isValid: true, isNatural: true };
    }
  }

  // Fallback attempt: try cronstrue in case of unusual cron format
  try {
    const desc = cronstrue.toString(raw);
    return { cron: raw, description: desc, isValid: true, isNatural: false };
  } catch {
    return {
      cron: raw,
      description: 'Could not parse schedule. Try e.g. "Every day at 9am" or "0 9 * * *"',
      isValid: false,
      isNatural: true,
    };
  }
}

/**
 * Formats any schedule string (cron expression or natural string) into human-readable text
 */
export function formatHumanSchedule(schedule: string): string {
  if (!schedule) return '—';
  try {
    return cronstrue.toString(schedule, { use24HourTimeFormat: false });
  } catch {
    const parsed = parseNaturalSchedule(schedule);
    if (parsed.isValid && parsed.description) {
      return parsed.description;
    }
    return schedule;
  }
}
