import { Check, Download } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ExportFormat, ExportOptions } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const DOWNLOADABLE: ExportFormat[] = ["txt", "md", "srt", "vtt", "json"];
const COPYABLE: ExportFormat[] = ["txt", "md"];

interface ExportMenuProps {
  urlFor: (format: ExportFormat, options: ExportOptions) => string;
  readText: (format: ExportFormat, options: ExportOptions) => Promise<string>;
}

/**
 * Copy sits above download on purpose: the transcript usually goes straight
 * into a note somewhere, and saving a file to open and select is the long way
 * round. Both render the same text, from the same endpoint.
 */
export function ExportMenu({ urlFor, readText }: ExportMenuProps) {
  const { t } = useTranslation();
  const [timestamps, setTimestamps] = useState(false);
  const [speakers, setSpeakers] = useState(true);
  const [copied, setCopied] = useState<ExportFormat | null>(null);

  const options: ExportOptions = { timestamps, speakers };

  const copy = async (format: ExportFormat) => {
    await navigator.clipboard.writeText(await readText(format, options));
    setCopied(format);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Download className="size-4" />
          {t("export.title")}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuCheckboxItem
          checked={timestamps}
          onCheckedChange={setTimestamps}
          onSelect={(event) => event.preventDefault()}
        >
          {t("export.timestamps")}
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={speakers}
          onCheckedChange={setSpeakers}
          onSelect={(event) => event.preventDefault()}
        >
          {t("export.speakers")}
        </DropdownMenuCheckboxItem>

        <DropdownMenuSeparator />
        <DropdownMenuLabel>{t("export.copy")}</DropdownMenuLabel>
        {COPYABLE.map((format) => (
          <DropdownMenuItem key={format} onSelect={() => void copy(format)}>
            {copied === format ? <Check className="size-4" /> : null}
            {t(`export.formats.${format}`)}
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator />
        <DropdownMenuLabel>{t("export.download")}</DropdownMenuLabel>
        {DOWNLOADABLE.map((format) => (
          <DropdownMenuItem key={format} asChild>
            {/* A plain link, so the browser saves it with the name the server
                chose instead of us inventing one in JavaScript. */}
            <a href={urlFor(format, { ...options, download: true })} download>
              {t(`export.formats.${format}`)}
            </a>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
