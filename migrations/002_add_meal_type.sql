-- Migration: 002_add_meal_type
-- Description: Add meal_type column to daily_meals table to support 4 meals per day
-- (breakfast, lunch, dinner, snacks) instead of 1 main meal per day.

-- Add meal_type column with default 'main' for backward compatibility with existing rows
ALTER TABLE daily_meals ADD COLUMN meal_type TEXT NOT NULL DEFAULT 'main';

-- Drop the old unique constraint (one meal per plan per day)
ALTER TABLE daily_meals DROP CONSTRAINT uq_daily_meals_plan_day;

-- Add new unique constraint (one meal per plan per day per meal_type)
ALTER TABLE daily_meals ADD CONSTRAINT uq_daily_meals_plan_day_type UNIQUE (meal_plan_id, day_of_week, meal_type);
