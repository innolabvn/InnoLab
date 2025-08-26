import { defineConfig } from 'cypress'
import * as security from './lib/insecurity'
import config from 'config'
import type { Memory as MemoryConfig, Product as ProductConfig } from './lib/config.types'
import * as utils from './lib/utils'
import * as otplib from 'otplib'

export default defineConfig({
  projectId: '3hrkhu',
  defaultCommandTimeout: 10000,
  retries: {
    runMode: 2
  },
  e2e: {
    baseUrl: 'http://localhost:3000',
    specPattern: 'test/cypress/e2e/**.spec.ts',
    downloadsFolder: 'test/cypress/downloads',
    fixturesFolder: false,
    supportFile: 'test/cypress/support/e2e.ts',
    setupNodeEvents (on: any) {
      on('task', {
        GenerateCoupon (discount: number) {
          return security.generateCoupon(discount)
        },
        GetBlueprint () {
          for (const product of config.get<ProductConfig[]>('products')) {
            if (product.fileForRetrieveBlueprintChallenge) {
              const blueprint = product.fileForRetrieveBlueprintChallenge
              return blueprint
            }
          }
        },
        GetChristmasProduct () {
          return config.get<ProductConfig[]>('products').filter(
            (product) => product.useForChristmasSpecialChallenge
          )[0]
        },
        GetCouponIntent () {
	  // Extract filename and sanitize it to prevent path traversal vulnerability
          const filename = utils.extractFilename(config.get('application.chatBot.trainingData'));
+	  // Require the training data using the sanitized filename
 	  const trainingData = require(`data/chatbot/${filename}`);
-          const couponIntent = trainingData.data.filter(
+          const couponIntent = trainingData.data?.filter(
             (data: { intent: string }) => data.intent === 'queries.couponCode'
           )[0]
           return couponIntent