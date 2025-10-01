import { test, expect } from '@playwright/test';

test('PagoPA checkout flow', async ({ page }) => {
  // Step 1: Open page
  console.log('🌍 Apro la pagina iniziale');
  await page.goto('https://checkout.pagopa.it/inserisci-dati-avviso');

  // Step 2: Fill Codice Avviso
  console.log('✍️ Inserisco Codice Avviso');
  await page.fill('#billCode', '301250000000044129');

  // Step 3: Fill Codice Fiscale Ente Creditore
  console.log('✍️ Inserisco Codice Fiscale Ente Creditore');
  await page.fill('#cf', '96289850586');

  // Step 4: Click Continua
  console.log('👉 Click su Continua');
  await page.click('#paymentNoticeButtonContinue');

  // Step 5: Click Vai al pagamento
  console.log('👉 Click su Vai al pagamento');
  await page.click('#paymentSummaryButtonPay');

  // Step 6: Fill email fields
  console.log('✍️ Inserisco Email e Conferma Email');
  await page.fill('#email', 'mariorossi@gmail.com');
  await page.fill('#confirmEmail', 'mariorossi@gmail.com');

  // Step 7: Click Carta di debito o credito
  console.log('👉 Click su Carta di debito o credito');
  await page.click('#paymentEmailPageButtonContinue');

  // Step 8: Vai alla pagina carta
  console.log('🌍 Apro la pagina inserimento carta');
  await page.goto('https://checkout.pagopa.it/inserisci-carta');

  console.log('⏳ Attendo che l\'iframe della carta sia visibile...');
  await page.locator('#frame_CARD_NUMBER').waitFor({ state: 'visible', timeout: 20000 });


  // Step 8a: Numero carta
  console.log('✍️ Inserisco Numero Carta');
  await cardNumberFrame.locator('#CARD_NUMBER').fill('4242424242424242');

  // Step 8b: Data di scadenza
  console.log('✍️ Inserisco Data di scadenza');
  const expFrame = page.frameLocator('#frame_EXPIRATION_DATE');
  await expFrame.locator('#EXPIRATION_DATE').fill('12/30');

  // Step 8c: CVV
  console.log('✍️ Inserisco CVV');
  const cvvFrame = page.frameLocator('#frame_SECURITY_CODE');
  await cvvFrame.locator('#SECURITY_CODE').fill('123');

  // Step 8d: Nome titolare
  console.log('✍️ Inserisco Nome Titolare');
  const nameFrame = page.frameLocator('#frame_CARDHOLDER_NAME');
  await nameFrame.locator('#CARDHOLDER_NAME').fill('Mario Rossi');

  // Step 9: Click Continua
  console.log('👉 Click su Continua');
  await page.click('#submit');

  // Step 10: Click Paga
  console.log('👉 Click su Paga');
  await page.click('#paymentCheckPageButtonPay');

  // Step 11: Assertion finale
  console.log('✅ Verifico che l\'URL sia quello di esito');
  await expect(page).toHaveURL('https://checkout.pagopa.it/esito');
});
