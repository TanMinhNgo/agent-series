import * as React from 'react';

import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select';
import { cn } from '@/lib/utils';

type Option = { value: string; label: React.ReactNode };

/** shadcn Select với API giống `<select>`: một value + danh sách option. */
function OptionSelect({
  value,
  options,
  onValueChange,
  className,
  id,
  disabled,
  required,
  'aria-label': ariaLabel,
}: {
  value: string;
  options: Option[];
  onValueChange: (value: string) => void;
  className?: string;
  id?: string;
  disabled?: boolean;
  required?: boolean;
  'aria-label'?: string;
}) {
  return (
    <Select value={value} disabled={disabled} required={required} onValueChange={(next) => onValueChange(next ?? '')}>
      <SelectTrigger id={id} aria-label={ariaLabel} className={cn('w-full bg-background', className)}>
        {options.find((option) => option.value === value)?.label}
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export { OptionSelect };
