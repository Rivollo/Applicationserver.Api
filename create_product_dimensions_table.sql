-- Create table for storing product dimensions
-- This table allows multiple dimensions per product (width, height, depth, etc.)
-- Each dimension has a type/name, value, unit, and associated hotspot IDs

CREATE TABLE IF NOT EXISTS public.tbl_product_dimensions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    product_id uuid NOT NULL,
    
    -- Dimension identification
    dimension_type text NOT NULL,  -- 'width', 'height', 'depth', or any custom dimension name
    dimension_name text NULL,  -- Optional display name (e.g., "Main Width", "Handle Width")
    
    -- Dimension values
    value numeric(10, 2) NOT NULL,
    unit text NOT NULL DEFAULT 'cm',
    
    -- Associated hotspots (start and end points for measurement)
    start_hotspot_id uuid NULL,
    end_hotspot_id uuid NULL,
    
    -- Ordering for multiple dimensions of the same type
    order_index integer NOT NULL DEFAULT 0,
    
    -- Audit fields
    created_by uuid NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_by uuid NULL,
    updated_date timestamp with time zone NULL,
    
    CONSTRAINT tbl_product_dimensions_pkey PRIMARY KEY (id),
    CONSTRAINT tbl_product_dimensions_product_id_fkey FOREIGN KEY (product_id) 
        REFERENCES public.tbl_products(id) ON DELETE CASCADE,
    CONSTRAINT tbl_product_dimensions_start_hotspot_fkey FOREIGN KEY (start_hotspot_id) 
        REFERENCES public.tbl_hotspots(id) ON DELETE SET NULL,
    CONSTRAINT tbl_product_dimensions_end_hotspot_fkey FOREIGN KEY (end_hotspot_id) 
        REFERENCES public.tbl_hotspots(id) ON DELETE SET NULL
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_product_dimensions_product_id 
    ON public.tbl_product_dimensions(product_id);
CREATE INDEX IF NOT EXISTS idx_product_dimensions_product_type 
    ON public.tbl_product_dimensions(product_id, dimension_type);
CREATE INDEX IF NOT EXISTS idx_product_dimensions_hotspots 
    ON public.tbl_product_dimensions(start_hotspot_id, end_hotspot_id);

-- Add comments
COMMENT ON TABLE public.tbl_product_dimensions IS 'Stores multiple product dimensions per product with values, units, and associated hotspot references';
COMMENT ON COLUMN public.tbl_product_dimensions.dimension_type IS 'Type of dimension (e.g., width, height, depth, diameter, etc.)';
COMMENT ON COLUMN public.tbl_product_dimensions.dimension_name IS 'Optional display name for the dimension';
COMMENT ON COLUMN public.tbl_product_dimensions.value IS 'Dimension value in the specified unit';
COMMENT ON COLUMN public.tbl_product_dimensions.unit IS 'Unit for the dimension (e.g., cm, m, in, ft)';
COMMENT ON COLUMN public.tbl_product_dimensions.start_hotspot_id IS 'Reference to hotspot marking the start of dimension measurement';
COMMENT ON COLUMN public.tbl_product_dimensions.end_hotspot_id IS 'Reference to hotspot marking the end of dimension measurement';
COMMENT ON COLUMN public.tbl_product_dimensions.order_index IS 'Order index for multiple dimensions of the same type';

