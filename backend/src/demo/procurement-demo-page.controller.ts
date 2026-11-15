import { Controller, Get, Res } from '@nestjs/common';
import type { Response } from 'express';
import { fileURLToPath } from 'node:url';

function sendAsset(response: Response, name: 'index.html' | 'style.css' | 'app.js') {
  response.set({
    'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  });
  // Fixed files only; no request path, directory serving or scientific artifacts.
  response.sendFile(fileURLToPath(new URL(`./public/procurement/${name}`, import.meta.url)));
}

@Controller('demo/procurement-v2')
export class ProcurementDemoPageController {
  @Get()
  page(@Res() response: Response) { sendAsset(response, 'index.html'); }

  @Get('assets/style.css')
  styles(@Res() response: Response) { sendAsset(response, 'style.css'); }

  @Get('assets/app.js')
  script(@Res() response: Response) { sendAsset(response, 'app.js'); }
}
