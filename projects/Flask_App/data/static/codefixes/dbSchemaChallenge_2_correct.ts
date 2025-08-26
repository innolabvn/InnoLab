import { Request, Response, NextFunction } from 'express'

const utils = require('../lib/utils')
const models = require('../models')
const security = require('../lib/security')
const challenges = require('../data/datacache').challenges
import { ErrorWithParent } from '../lib/types/error'

export function searchProducts () {
  return (req: Request, res: Response, next: NextFunction) => {
    let criteria: any = req.query.q === 'undefined' ? '' : req.query.q ?? ''
    criteria = (criteria.length <= 200) ? criteria : criteria.substring(0, 200)
    // Fixed: Use Sequelize's parameterized queries to prevent SQL injection.
    models.sequelize.query(
        `SELECT * FROM Products WHERE ((name LIKE :nameCriteria OR description LIKE :descriptionCriteria) AND deletedAt IS NULL) ORDER BY name`,
        { replacements: { nameCriteria: `%${criteria}%`, descriptionCriteria: `%${criteria}%` } }
      ).then(([products]: any) => {
        const dataString = JSON.stringify(products)
        for (let i = 0; i < products.length; i++) {
          products[i].name = req.__(products[i].name)
          products[i].description = req.__(products[i].description)
        }
        res.json(utils.queryResultToJson(products))
      }).catch((error: ErrorWithParent) => {
        next(error.parent)
      })
  }
}