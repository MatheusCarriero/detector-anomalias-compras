import { Controller, Get, Res } from '@nestjs/common';
import type { Response } from 'express';
import { fileURLToPath } from 'node:url';

function sendAsset(response: Response, name: 'index.html' | 'style.css' | 'app.js' | 'purchase.js') {
  response.set({
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  });
  // Only named assets are public. No directory listing or request path input.
  response.sendFile(fileURLToPath(new URL(`./public/${name}`, import.meta.url)));
}

@Controller()
export class InvoiceDemoPageController {
  @Get('/')
  page(@Res() response: Response) {
    sendAsset(response, 'index.html');
  }

  @Get('/demo/assets/style.css')
  styles(@Res() response: Response) {
    sendAsset(response, 'style.css');
  }

  @Get('/demo/assets/app.js')
  script(@Res() response: Response) {
    sendAsset(response, 'app.js');
  }

  @Get('/demo/assets/purchase.js')
  purchaseScript(@Res() response: Response) {
    sendAsset(response, 'purchase.js');
  }
}
