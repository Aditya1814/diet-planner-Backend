-- Migration: 001_initial_schema
-- Description: Create initial database schema for Diet Planner
-- Tables: grocery_lists, grocery_items, dietary_preferences, meal_plans, daily_meals, meal_ingredients
-- Enables Row Level Security (RLS) on all tables

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Table: grocery_lists
-- ============================================================
CREATE TABLE grocery_lists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_grocery_lists_user_week UNIQUE (user_id, week_start_date)
);

CREATE INDEX idx_grocery_lists_user_id ON grocery_lists(user_id);
CREATE INDEX idx_grocery_lists_week_start_date ON grocery_lists(week_start_date);

-- ============================================================
-- Table: grocery_items
-- ============================================================
CREATE TABLE grocery_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    grocery_list_id UUID NOT NULL REFERENCES grocery_lists(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity DECIMAL NOT NULL,
    unit TEXT NOT NULL,
    remaining_quantity DECIMAL NOT NULL
);

CREATE INDEX idx_grocery_items_grocery_list_id ON grocery_items(grocery_list_id);

-- ============================================================
-- Table: dietary_preferences
-- ============================================================
CREATE TABLE dietary_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    grocery_list_id UUID NOT NULL REFERENCES grocery_lists(id) ON DELETE CASCADE,
    preference TEXT NOT NULL
);

CREATE INDEX idx_dietary_preferences_grocery_list_id ON dietary_preferences(grocery_list_id);

-- ============================================================
-- Table: meal_plans
-- ============================================================
CREATE TABLE meal_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_meal_plans_user_week UNIQUE (user_id, week_start_date)
);

CREATE INDEX idx_meal_plans_user_id ON meal_plans(user_id);
CREATE INDEX idx_meal_plans_week_start_date ON meal_plans(week_start_date);

-- ============================================================
-- Table: daily_meals
-- ============================================================
CREATE TABLE daily_meals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meal_plan_id UUID NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
    day_of_week TEXT NOT NULL,
    meal_date DATE NOT NULL,
    meal_name TEXT NOT NULL,
    instructions TEXT NOT NULL,
    image_url TEXT,
    is_preserved BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_daily_meals_plan_day UNIQUE (meal_plan_id, day_of_week)
);

CREATE INDEX idx_daily_meals_meal_plan_id ON daily_meals(meal_plan_id);

-- ============================================================
-- Table: meal_ingredients
-- ============================================================
CREATE TABLE meal_ingredients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    daily_meal_id UUID NOT NULL REFERENCES daily_meals(id) ON DELETE CASCADE,
    ingredient_name TEXT NOT NULL,
    quantity DECIMAL NOT NULL,
    unit TEXT NOT NULL
);

CREATE INDEX idx_meal_ingredients_daily_meal_id ON meal_ingredients(daily_meal_id);

-- ============================================================
-- Row Level Security (RLS) Policies
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE grocery_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE grocery_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE dietary_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE meal_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_meals ENABLE ROW LEVEL SECURITY;
ALTER TABLE meal_ingredients ENABLE ROW LEVEL SECURITY;


-- RLS Policies for grocery_lists
CREATE POLICY "Users can view their own grocery lists"
    ON grocery_lists FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own grocery lists"
    ON grocery_lists FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own grocery lists"
    ON grocery_lists FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own grocery lists"
    ON grocery_lists FOR DELETE
    USING (auth.uid() = user_id);

-- RLS Policies for grocery_items (access via grocery_list ownership)
CREATE POLICY "Users can view their own grocery items"
    ON grocery_items FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = grocery_items.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert their own grocery items"
    ON grocery_items FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = grocery_items.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update their own grocery items"
    ON grocery_items FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = grocery_items.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = grocery_items.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete their own grocery items"
    ON grocery_items FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = grocery_items.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

-- RLS Policies for dietary_preferences (access via grocery_list ownership)
CREATE POLICY "Users can view their own dietary preferences"
    ON dietary_preferences FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = dietary_preferences.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert their own dietary preferences"
    ON dietary_preferences FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = dietary_preferences.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update their own dietary preferences"
    ON dietary_preferences FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = dietary_preferences.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = dietary_preferences.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete their own dietary preferences"
    ON dietary_preferences FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM grocery_lists
            WHERE grocery_lists.id = dietary_preferences.grocery_list_id
            AND grocery_lists.user_id = auth.uid()
        )
    );

-- RLS Policies for meal_plans
CREATE POLICY "Users can view their own meal plans"
    ON meal_plans FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own meal plans"
    ON meal_plans FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own meal plans"
    ON meal_plans FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own meal plans"
    ON meal_plans FOR DELETE
    USING (auth.uid() = user_id);

-- RLS Policies for daily_meals (access via meal_plan ownership)
CREATE POLICY "Users can view their own daily meals"
    ON daily_meals FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM meal_plans
            WHERE meal_plans.id = daily_meals.meal_plan_id
            AND meal_plans.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert their own daily meals"
    ON daily_meals FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM meal_plans
            WHERE meal_plans.id = daily_meals.meal_plan_id
            AND meal_plans.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update their own daily meals"
    ON daily_meals FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM meal_plans
            WHERE meal_plans.id = daily_meals.meal_plan_id
            AND meal_plans.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM meal_plans
            WHERE meal_plans.id = daily_meals.meal_plan_id
            AND meal_plans.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete their own daily meals"
    ON daily_meals FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM meal_plans
            WHERE meal_plans.id = daily_meals.meal_plan_id
            AND meal_plans.user_id = auth.uid()
        )
    );

-- RLS Policies for meal_ingredients (access via meal_plan → daily_meal ownership)
CREATE POLICY "Users can view their own meal ingredients"
    ON meal_ingredients FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM daily_meals
            JOIN meal_plans ON meal_plans.id = daily_meals.meal_plan_id
            WHERE daily_meals.id = meal_ingredients.daily_meal_id
            AND meal_plans.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert their own meal ingredients"
    ON meal_ingredients FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM daily_meals
            JOIN meal_plans ON meal_plans.id = daily_meals.meal_plan_id
            WHERE daily_meals.id = meal_ingredients.daily_meal_id
            AND meal_plans.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update their own meal ingredients"
    ON meal_ingredients FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM daily_meals
            JOIN meal_plans ON meal_plans.id = daily_meals.meal_plan_id
            WHERE daily_meals.id = meal_ingredients.daily_meal_id
            AND meal_plans.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM daily_meals
            JOIN meal_plans ON meal_plans.id = daily_meals.meal_plan_id
            WHERE daily_meals.id = meal_ingredients.daily_meal_id
            AND meal_plans.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete their own meal ingredients"
    ON meal_ingredients FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM daily_meals
            JOIN meal_plans ON meal_plans.id = daily_meals.meal_plan_id
            WHERE daily_meals.id = meal_ingredients.daily_meal_id
            AND meal_plans.user_id = auth.uid()
        )
    );
